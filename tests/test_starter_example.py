"""The starter example is the reference material /tramat:init composes from —
it must actually be a valid, doctor-clean repo (Tier-0 execution is proven
separately by the golden workflow)."""

from __future__ import annotations

import ast
import json

import yaml

import doctor
from conftest import STARTER


def test_expected_files_present():
    for rel in (
        "tramat.yml",
        "databricks.yml",
        "pyproject.toml",
        ".pre-commit-config.yaml",
        ".gitignore",
        "CLAUDE.md",
        "AGENTS.md",
        "README.md",
        "docs/runbook.md",
        ".github/workflows/pr-checks.yml",
        "src/starter_lakehouse/env.py",
        "src/starter_lakehouse/delta.py",
        "src/starter_lakehouse/merge.py",
        "src/starter_lakehouse/hashing.py",
        "src/starter_lakehouse/qa.py",
        "tests/conftest.py",
        "tests/test_qa.py",
    ):
        assert (STARTER / rel).exists(), rel


def test_yaml_files_parse():
    for rel in ("tramat.yml", "databricks.yml", ".github/workflows/pr-checks.yml", ".pre-commit-config.yaml"):
        yaml.safe_load((STARTER / rel).read_text(encoding="utf-8"))


def test_python_files_parse():
    py_files = [p for p in STARTER.rglob("*.py") if ".venv" not in p.parts]
    assert len(py_files) >= 12
    for path in py_files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_manifest_is_schema_valid():
    data = yaml.safe_load((STARTER / "tramat.yml").read_text(encoding="utf-8"))
    schema = json.loads(doctor.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert doctor.validate_schema(data, schema, schema) == []


def test_doctor_repo_checks_all_green():
    doc = doctor.Doctor(repo=STARTER)
    code = doc.run(repo_only=True)
    problems = [(c.name, c.status, c.detail) for c in doc.checks if c.status in ("error", "warn")]
    assert code == 0 and not problems, problems


def test_bundle_follows_conventions():
    bundle = yaml.safe_load((STARTER / "databricks.yml").read_text(encoding="utf-8"))
    assert bundle["run_as"]["service_principal_name"]
    assert bundle["targets"]["prod"]["mode"] == "production"
    catalogs = {t: v.get("variables", {}).get("CATALOG") for t, v in bundle["targets"].items()}
    assert len(set(catalogs.values())) == len(catalogs), "each target needs its own catalog"


def test_no_leftover_template_placeholders():
    for path in STARTER.rglob("*"):
        if path.is_file() and ".venv" not in path.parts:
            assert "{{tramat." not in path.read_text(encoding="utf-8", errors="ignore"), path
