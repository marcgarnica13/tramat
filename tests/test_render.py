"""Tests for scripts/render.py and the repo template group."""

from __future__ import annotations

import ast
import json

import pytest
import yaml

import render
from conftest import REPO_VARS


# ---------- substitution semantics ----------


def test_substitute_basic():
    assert render.substitute("hi {{tramat.name}}!", {"name": "marc"}, "t") == "hi marc!"


def test_substitute_missing_var_errors():
    with pytest.raises(render.RenderError, match="missing variable 'name'"):
        render.substitute("{{tramat.name}}", {}, "t")


def test_substitute_leaves_foreign_placeholders_alone():
    """Databricks' own templating must pass through untouched."""
    text = "id: {{job.run_id}} host: ${var.host} gha: ${{ secrets.TOKEN }}"
    assert render.substitute(text, {}, "t") == text


def test_substitute_rejects_malformed_tramat_placeholder():
    with pytest.raises(render.RenderError, match="unrendered placeholder"):
        render.substitute("{{tramat.BadCase}}", {}, "t")


def test_unsafe_target_path_rejected(tmp_path):
    entry = {"src": "_empty.tmpl", "target": "../escape", "tier": "seeded"}
    with pytest.raises(render.RenderError, match="unsafe target"):
        render.render_file("repo", entry, {})


# ---------- group manifest ----------


def test_repo_group_loads_and_lists():
    manifest = render.load_group("repo")
    assert manifest["id"] == "repo"
    targets = [e["target"] for e in manifest["files"]]
    assert "tramat.yml" in targets and "databricks.yml" in targets
    assert any(g["group"] == "repo" for g in render.cmd_list())


def test_unknown_group_errors():
    with pytest.raises(render.RenderError, match="unknown template group"):
        render.load_group("nope")


def test_repo_group_vars_are_exactly_the_documented_set():
    assert render.group_vars("repo") == set(REPO_VARS)


# ---------- apply ----------


def test_apply_missing_var_is_error(tmp_path):
    with pytest.raises(render.RenderError, match="needs variables"):
        render.cmd_apply("repo", tmp_path, {"project_name": "x"}, force=False)
    assert not (tmp_path / "tramat.yml").exists(), "no partial writes on error"


def test_apply_unknown_var_is_error(tmp_path):
    with pytest.raises(render.RenderError, match="not used by group"):
        render.cmd_apply("repo", tmp_path, dict(REPO_VARS, extra="x"), force=False)


def test_apply_renders_everything(rendered_repo):
    package = REPO_VARS["package"]
    for expected in (
        "tramat.yml",
        "databricks.yml",
        "pyproject.toml",
        ".github/workflows/pr-checks.yml",
        f"src/{package}/env.py",
        f"src/{package}/qa.py",
        "tests/test_merge.py",
        ".tramat/applied.json",
    ):
        assert (rendered_repo / expected).exists(), expected


def test_applied_json_records_tiers_and_vars(rendered_repo):
    applied = json.loads((rendered_repo / ".tramat" / "applied.json").read_text())
    files = applied["files"]
    assert files["databricks.yml"]["tier"] == "enforced"
    assert files["tramat.yml"]["tier"] == "merged"
    assert files[f"src/{REPO_VARS['package']}/env.py"]["tier"] == "seeded"
    # stored vars are the subset each file actually uses, enough to re-render
    assert files["databricks.yml"]["vars"]["workspace_host"] == REPO_VARS["workspace_host"]
    assert "workspace_host" not in files["tramat.yml"]["vars"]
    for entry in files.values():
        assert entry["sha256"] and entry["template"] and entry["rendered_at"]


def test_no_placeholder_survives_rendering(rendered_repo):
    for path in rendered_repo.rglob("*"):
        if path.is_file():
            assert "{{tramat." not in path.read_text(encoding="utf-8"), path


def test_seeded_files_never_overwritten(rendered_repo):
    marker = "# user owns this now\n"
    readme = rendered_repo / "README.md"
    readme.write_text(marker)
    results = render.cmd_apply("repo", rendered_repo, dict(REPO_VARS), force=True)
    assert readme.read_text() == marker
    assert {r["action"] for r in results if r["tier"] != "enforced"} == {"kept"}


def test_enforced_reapply_needs_force(rendered_repo):
    with pytest.raises(render.RenderError, match="--force"):
        render.cmd_apply("repo", rendered_repo, dict(REPO_VARS), force=False)
    render.cmd_apply("repo", rendered_repo, dict(REPO_VARS), force=True)  # ok


# ---------- check (drift) ----------


def test_check_clean_after_apply(rendered_repo):
    findings = render.cmd_check(rendered_repo)
    assert findings, "enforced files must be tracked"
    assert all(f["status"] == "ok" for f in findings)


def test_check_flags_hand_edit(rendered_repo):
    target = rendered_repo / "databricks.yml"
    target.write_text(target.read_text() + "\n# sneaky edit\n")
    statuses = {f["target"]: f["status"] for f in render.cmd_check(rendered_repo)}
    assert statuses["databricks.yml"] == "edited"


def test_check_flags_missing(rendered_repo):
    (rendered_repo / "databricks.yml").unlink()
    statuses = {f["target"]: f["status"] for f in render.cmd_check(rendered_repo)}
    assert statuses["databricks.yml"] == "missing"


def test_check_ignores_seeded_edits(rendered_repo):
    (rendered_repo / "README.md").write_text("rewritten\n")
    assert all(f["status"] == "ok" for f in render.cmd_check(rendered_repo))


# ---------- rendered content is actually valid ----------


def test_rendered_yaml_parses(rendered_repo):
    for name in ("tramat.yml", "databricks.yml", ".github/workflows/pr-checks.yml", ".pre-commit-config.yaml"):
        yaml.safe_load((rendered_repo / name).read_text())


def test_rendered_python_parses(rendered_repo):
    py_files = list(rendered_repo.rglob("*.py"))
    assert len(py_files) >= 12
    for path in py_files:
        ast.parse(path.read_text(), filename=str(path))


def test_rendered_manifest_passes_schema_and_doctor(rendered_repo):
    import doctor

    data = yaml.safe_load((rendered_repo / "tramat.yml").read_text())
    schema = json.loads(doctor.SCHEMA_PATH.read_text())
    assert doctor.validate_schema(data, schema, schema) == []

    doc = doctor.Doctor(repo=rendered_repo)
    code = doc.run(repo_only=True)
    problems = [(c.name, c.detail) for c in doc.checks if c.status == "error"]
    assert code == 0 and not problems, problems


def test_rendered_bundle_references_expected_values(rendered_repo):
    bundle = yaml.safe_load((rendered_repo / "databricks.yml").read_text())
    assert bundle["bundle"]["name"] == REPO_VARS["project_name"]
    assert bundle["run_as"]["service_principal_name"] == REPO_VARS["run_as_sp"]
    assert bundle["targets"]["prod"]["mode"] == "production"
    assert bundle["targets"]["prod"]["variables"]["CATALOG"] == REPO_VARS["prod_catalog"]
