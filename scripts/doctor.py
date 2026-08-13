"""Machine checks for a tramat environment and repo.

Plugin-internal. Runs standalone (stdlib + PyYAML, the one declared
dependency — and its absence is itself a finding here, not a crash):

    python3 scripts/doctor.py                  # check env + repo in cwd
    python3 scripts/doctor.py /path/to/repo    # check another repo
    python3 scripts/doctor.py --json           # machine-readable output
    python3 scripts/doctor.py --profile PROD   # also verify auth for one profile

Environment checks: Python version, PyYAML, Databricks CLI, the official
databricks plugin at a tested version (via `databricks aitools list -o json`),
auth profiles (never auto-selected — validity is only probed for a profile the
user names), codex binary for the second-opinion gate.

Repo checks: tramat.yml present, schema-valid against
schemas/tramat.schema.json, and the graph section's semantic validation
(delegated to graph.py — waves, single-primary, signed idempotency).

Databricks *workspace* health is not checked here — that is
/databricks:doctor's job; tramat delegates, never vendors.
"""

from __future__ import annotations

import argparse
import configparser
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PLUGIN_ROOT / "schemas" / "tramat.schema.json"

# Databricks plugin release range this tramat version is tested against.
# Upstream skill drift is proven (names changed twice across channels
# already), so newer-than-tested is a warn, not a pass.
DB_PLUGIN_MIN = (0, 2, 0)
DB_PLUGIN_TESTED = (0, 2, 10)

# Skills tramat references by name (plan decision #3). Old names the upstream
# catalog has used for the same skill map to their current name here.
DB_REQUIRED_SKILLS = [
    "databricks-core",
    "databricks-dabs",
    "databricks-pipelines",
    "databricks-jobs",
    "databricks-metric-views",
    "databricks-execution-compute",
    "databricks-ml-training",
    "databricks-unity-catalog",
    "databricks-dbsql",
    "databricks-data-discovery",
    "databricks-lakeflow-connect",
    "databricks-genie-agents",
]
DB_SKILL_ALIASES = {
    "databricks-bundles": "databricks-dabs",
    "databricks-spark-declarative-pipelines": "databricks-pipelines",
    # catalog says databricks-genie while the 0.2.10 plugin ships
    # databricks-genie-agents — third observed rename, either satisfies
    "databricks-genie": "databricks-genie-agents",
}

SEVERITY_ORDER = ("error", "warn", "info", "ok", "skip")


@dataclass
class Check:
    name: str
    status: str  # ok | info | warn | error | skip
    detail: str
    hint: str = ""


@dataclass
class Doctor:
    repo: Path
    profile: str | None = None
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str, hint: str = "") -> None:
        self.checks.append(Check(name, status, detail, hint))

    # ---------- environment ----------

    def check_python(self) -> None:
        v = sys.version_info
        if (v.major, v.minor) >= (3, 10):
            self.add("python", "ok", f"{v.major}.{v.minor}.{v.micro}")
        else:
            self.add("python", "error", f"{v.major}.{v.minor} < 3.10 required")

    def check_pyyaml(self) -> bool:
        try:
            import yaml  # noqa: F401

            self.add("pyyaml", "ok", "importable (the one declared dependency)")
            return True
        except ImportError:
            self.add("pyyaml", "error", "not importable", "pip install pyyaml")
            return False

    def check_databricks_cli(self) -> bool:
        exe = shutil.which("databricks")
        if not exe:
            self.add(
                "databricks-cli",
                "error",
                "not on PATH",
                "install the Databricks CLI: https://docs.databricks.com/dev-tools/cli/",
            )
            return False
        try:
            out = subprocess.run(
                ["databricks", "--version"], capture_output=True, text=True, timeout=10
            )
            self.add("databricks-cli", "ok", out.stdout.strip() or exe)
        except (subprocess.TimeoutExpired, OSError) as e:
            self.add("databricks-cli", "warn", f"present but --version failed: {e}")
        return True

    def check_databricks_plugin(self, cli_present: bool) -> None:
        if not cli_present:
            self.add("databricks-plugin", "skip", "needs the Databricks CLI")
            return
        try:
            out = subprocess.run(
                ["databricks", "aitools", "list", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            data = json.loads(out.stdout)
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
            self.add(
                "databricks-plugin",
                "error",
                f"`databricks aitools list -o json` failed ({e})",
                "install the official plugin: databricks aitools install",
            )
            return

        release = str(data.get("release", ""))
        try:
            rel = tuple(int(x) for x in release.split("."))
        except ValueError:
            rel = ()
        if not rel or rel < DB_PLUGIN_MIN:
            self.add(
                "databricks-plugin",
                "error",
                f"release {release or 'unknown'} < minimum {'.'.join(map(str, DB_PLUGIN_MIN))}",
                "databricks aitools install",
            )
        elif rel > DB_PLUGIN_TESTED:
            self.add(
                "databricks-plugin",
                "warn",
                f"release {release} is newer than tested "
                f"{'.'.join(map(str, DB_PLUGIN_TESTED))} — skill names drift upstream; "
                "watch for renames",
            )
        else:
            self.add("databricks-plugin", "ok", f"release {release}")

        names = {s.get("name") for s in data.get("skills", [])}
        # a required skill counts as present under its current or any old name
        missing = [
            r
            for r in DB_REQUIRED_SKILLS
            if r not in names
            and not any(old in names for old, new in DB_SKILL_ALIASES.items() if new == r)
        ]
        if missing:
            self.add(
                "databricks-skills",
                "error",
                f"missing from the catalog: {', '.join(missing)}",
                "upstream may have renamed them — check `databricks aitools list` "
                "and report a tramat alias-map gap",
            )
        else:
            self.add(
                "databricks-skills", "ok", f"all {len(DB_REQUIRED_SKILLS)} required skills present"
            )

    def check_auth(self) -> None:
        cfg_path = Path.home() / ".databrickscfg"
        if not cfg_path.exists():
            self.add(
                "auth-profiles",
                "warn",
                "~/.databrickscfg not found",
                "databricks auth login --host <workspace-url>",
            )
            return
        cfg = configparser.ConfigParser()
        try:
            cfg.read(cfg_path)
        except configparser.Error as e:
            self.add("auth-profiles", "error", f"~/.databrickscfg unparseable: {e}")
            return
        # dunder sections (e.g. __settings__) are CLI-internal, not profiles
        profiles = [s for s in cfg.sections() if not s.startswith("__")] + (
            ["DEFAULT"] if cfg.defaults() else []
        )
        if not profiles:
            self.add("auth-profiles", "warn", "no profiles configured")
            return
        self.add(
            "auth-profiles",
            "ok",
            f"{len(profiles)} profile(s): {', '.join(profiles)} "
            "(validity not probed — name one with --profile)",
        )
        if self.profile:
            if self.profile not in profiles:
                self.add("auth-validity", "error", f"profile {self.profile!r} not in config")
                return
            try:
                out = subprocess.run(
                    ["databricks", "auth", "describe", "--profile", self.profile],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if out.returncode == 0:
                    self.add("auth-validity", "ok", f"profile {self.profile!r} authenticates")
                else:
                    self.add(
                        "auth-validity",
                        "error",
                        f"profile {self.profile!r}: {out.stderr.strip().splitlines()[-1] if out.stderr.strip() else 'auth describe failed'}",
                        f"databricks auth login --profile {self.profile}",
                    )
            except (subprocess.TimeoutExpired, OSError) as e:
                self.add("auth-validity", "warn", f"could not probe: {e}")

    def check_codex(self) -> None:
        exe = shutil.which("codex")
        if exe:
            self.add(
                "codex",
                "info",
                "codex binary detected — the cross-AI second-opinion gate is available",
                "enable it in tramat.yml: review.second_opinion.enabled: true",
            )
        else:
            self.add("codex", "info", "no codex binary — second-opinion gate unavailable (optional)")

    # ---------- repo ----------

    def check_manifest(self, yaml_ok: bool) -> None:
        manifest = self.repo / "tramat.yml"
        if not manifest.exists():
            if (self.repo / "databricks.yml").exists():
                self.add(
                    "manifest",
                    "warn",
                    "Databricks bundle repo without tramat.yml",
                    "brownfield: /tramat:onboard will survey conventions and write one "
                    "(greenfield: /tramat:init)",
                )
            else:
                self.add("manifest", "info", "no tramat.yml (not a tramat repo)")
            self.add("manifest-schema", "skip", "no manifest")
            self.add("graph", "skip", "no manifest")
            return
        if not yaml_ok:
            self.add("manifest", "warn", "tramat.yml present but PyYAML missing — cannot parse")
            self.add("manifest-schema", "skip", "PyYAML missing")
            self.add("graph", "skip", "PyYAML missing")
            return

        import yaml

        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            self.add("manifest", "error", f"tramat.yml does not parse: {e}")
            self.add("manifest-schema", "skip", "manifest unparseable")
            self.add("graph", "skip", "manifest unparseable")
            return
        if not isinstance(data, dict):
            self.add("manifest", "error", "tramat.yml is not a mapping")
            return
        self.add("manifest", "ok", "tramat.yml parses")

        schema_ok = True
        try:
            schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            self.add("manifest-schema", "error", f"cannot load {SCHEMA_PATH.name}: {e}")
        else:
            errors = validate_schema(data, schema, schema)
            if errors:
                shown = "; ".join(errors[:5]) + (f" (+{len(errors) - 5} more)" if len(errors) > 5 else "")
                self.add("manifest-schema", "error", shown)
                schema_ok = False
            else:
                self.add("manifest-schema", "ok", "valid against tramat.schema.json")

        if schema_ok:
            self.check_graph(manifest, data)
        else:
            self.add("graph", "skip", "fix schema errors first")

    def check_graph(self, manifest: Path, data: dict) -> None:
        if not isinstance(data.get("graph"), dict):
            self.add("graph", "info", "no graph: section yet")
            return
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            import graph as graph_mod

            g = graph_mod.Graph.load(manifest)
            findings = g.validate()
        except Exception as e:  # graph.py owns its own CLI; never crash doctor
            self.add("graph", "error", f"graph.py validation crashed: {e}")
            return
        n_err = sum(1 for f in findings if f.severity == "error")
        n_warn = sum(1 for f in findings if f.severity == "warn")
        detail = f"{len(g.steps)} steps; {n_err} error(s), {n_warn} warning(s)"
        if n_err:
            first = next(f for f in findings if f.severity == "error")
            self.add("graph", "error", f"{detail} — first: {first.step}: {first.message}",
                     f"python3 scripts/graph.py {manifest}")
        elif n_warn:
            self.add("graph", "warn", detail, f"python3 scripts/graph.py {manifest}")
        else:
            self.add("graph", "ok", detail)

    # ---------- run ----------

    def run(self) -> int:
        self.check_python()
        yaml_ok = self.check_pyyaml()
        cli = self.check_databricks_cli()
        self.check_databricks_plugin(cli)
        self.check_auth()
        self.check_codex()
        self.check_manifest(yaml_ok)
        return 1 if any(c.status == "error" for c in self.checks) else 0


def validate_schema(value, schema, root, path="$") -> list[str]:
    """Minimal JSON Schema subset validator: const, type, enum, required,
    properties, items, $ref (local #/$defs only). Enough for
    tramat.schema.json — semantics beyond shape belong to graph.py, not here.
    YAML timestamps count as strings.
    """
    import datetime

    errors: list[str] = []
    if "$ref" in schema:
        ref = schema["$ref"]
        node = root
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
        return validate_schema(value, node, root, path)

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not one of {schema['enum']}")

    types = schema.get("type")
    if types:
        types = [types] if isinstance(types, str) else types
        py = {
            "object": dict,
            "array": list,
            "string": (str, datetime.date, datetime.datetime),
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "null": type(None),
        }
        # bool is an int in Python; don't let it satisfy number/integer
        matched = any(
            isinstance(value, py[t]) and not (t in ("number", "integer") and isinstance(value, bool))
            for t in types
            if t in py
        )
        if not matched:
            errors.append(f"{path}: expected {'/'.join(types)}, got {type(value).__name__}")
            return errors  # structural checks below would just cascade

    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required key {req!r}")
        for key, sub in (schema.get("properties") or {}).items():
            if key in value:
                errors.extend(validate_schema(value[key], sub, root, f"{path}.{key}"))
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errors.extend(validate_schema(item, schema["items"], root, f"{path}[{i}]"))
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="tramat environment + repo checks")
    ap.add_argument("repo", type=Path, nargs="?", default=Path.cwd())
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--profile",
        help="also probe auth validity for this named profile (never auto-selected)",
    )
    args = ap.parse_args()

    doc = Doctor(repo=args.repo.resolve(), profile=args.profile)
    code = doc.run()

    if args.json:
        print(
            json.dumps(
                {
                    "repo": str(doc.repo),
                    "ok": code == 0,
                    "checks": [vars(c) for c in doc.checks],
                },
                indent=2,
            )
        )
        return code

    width = max(len(c.name) for c in doc.checks)
    icon = {"ok": "✓", "info": "·", "warn": "!", "error": "✗", "skip": "-"}
    for c in doc.checks:
        print(f"{icon[c.status]} {c.name:<{width}}  {c.detail}")
        if c.hint and c.status in ("warn", "error", "info"):
            print(f"  {'':<{width}}  ↳ {c.hint}")
    n_err = sum(1 for c in doc.checks if c.status == "error")
    n_warn = sum(1 for c in doc.checks if c.status == "warn")
    print(f"\n{n_err} error(s), {n_warn} warning(s)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
