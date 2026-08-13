"""Build a repo map from the Databricks Asset Bundle down to shared modules.

    databricks.yml + resources/*.yml
        -> jobs -> tasks -> entrypoint .py
            -> local imports (transitive)
                -> src/utils, src/models, src/checks ...

Nothing to annotate. The bundle already declares task -> file, and Python
imports already declare file -> module. This reads both.

The reverse index is the point: "who uses this helper" is the question an
agent cannot answer by querying anything, and the one that stops it writing
a fourth copy of a function that already exists.

    python3 scripts/repomap.py --bundle databricks.yml --src src --out docs/repo
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

TASK_KINDS = (
    ("spark_python_task", "python_file"),
    ("notebook_task", "notebook_path"),
    ("python_wheel_task", "entry_point"),
    ("sql_task", None),
    ("pipeline_task", None),
    ("run_job_task", None),
)


@dataclass
class Task:
    job: str
    key: str
    kind: str
    target: str | None            # raw value from the bundle
    entrypoint: Path | None       # resolved file, if resolvable
    depends_on: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class Module:
    path: Path
    docstring: str
    defs: list[str]
    classes: list[str]
    imports: set[str] = field(default_factory=set)


# --------------------------------------------------------------------------
# bundle
# --------------------------------------------------------------------------

def load_bundle(root: Path) -> tuple[dict[str, Any], list[Path]]:
    """Merge databricks.yml with its include: globs.

    Also returns every directory a resource file came from. Relative paths in
    a resource file resolve against that file's directory, not the bundle
    root, so we need them all as candidate bases.
    """
    merged: dict[str, Any] = {}
    files = [root]
    base = yaml.safe_load(root.read_text(encoding="utf-8")) or {}
    for pattern in base.get("include", []) or []:
        files.extend(sorted(root.parent.glob(pattern)))

    bases: list[Path] = []
    for f in files:
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            print(f"warn: cannot read {f}: {exc}", file=sys.stderr)
            continue
        _deep_merge(merged, doc)
        d = f.parent.resolve()
        if d not in bases:
            bases.append(d)
    return merged, bases


def _deep_merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v


def extract_tasks(bundle: dict[str, Any], bases: list[Path], repo_root: Path) -> list[Task]:
    tasks: list[Task] = []
    jobs = ((bundle.get("resources") or {}).get("jobs") or {})

    for job_name, job in jobs.items():
        for raw in _iter_tasks(job.get("tasks") or []):
            kind, target, note = "unknown", None, ""
            for key, field_name in TASK_KINDS:
                if key not in raw:
                    continue
                kind = key
                if field_name is None:
                    note = f"{key} — no python entrypoint"
                    break
                target = (raw[key] or {}).get(field_name)
                if key == "python_wheel_task" and target:
                    note = f"wheel entry_point {target!r}; resolve via the package, not a path"
                break

            entry = _resolve(target, bases, repo_root) if kind in (
                "spark_python_task",
                "notebook_task",
            ) else None
            if target and kind in ("spark_python_task", "notebook_task") and entry is None:
                note = f"declared {target!r} but no such file"

            tasks.append(
                Task(
                    job=job_name,
                    key=raw.get("task_key", "<unkeyed>"),
                    kind=kind,
                    target=target,
                    entrypoint=entry,
                    depends_on=[d.get("task_key") for d in (raw.get("depends_on") or [])],
                    note=note,
                )
            )
    return tasks


def _iter_tasks(tasks: list[dict]):
    """Flatten for_each_task wrappers, keeping the wrapper's key AND depends_on —
    the DAG edges live on the wrapper, not the inner task."""
    for t in tasks:
        if "for_each_task" in t:
            inner = (t["for_each_task"] or {}).get("task")
            if inner:
                yield {
                    **inner,
                    "task_key": t.get("task_key", inner.get("task_key")),
                    "depends_on": t.get("depends_on", inner.get("depends_on")),
                }
            continue
        yield t


def _resolve(target: str | None, bases: list[Path], repo_root: Path) -> Path | None:
    """Resolve a bundle-declared path, rejecting anything outside the repo.

    Without the containment check a `../` path can escape the repo and match
    an unrelated file, which is worse than not resolving at all.
    """
    if not target:
        return None
    clean = target.replace("${workspace.file_path}/", "").lstrip("/")
    for base in list(bases) + [repo_root]:
        for cand in (base / clean, base / f"{clean}.py"):
            try:
                resolved = cand.resolve()
            except OSError:
                continue
            if not resolved.is_file():
                continue
            if not resolved.is_relative_to(repo_root):
                continue
            return resolved
    return None


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


# --------------------------------------------------------------------------
# modules
# --------------------------------------------------------------------------

def scan_module(path: Path, src_root: Path) -> Module:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        print(f"warn: cannot parse {path}: {exc}", file=sys.stderr)
        return Module(path=path, docstring="", defs=[], classes=[])

    doc = (ast.get_docstring(tree) or "").strip().split("\n\n")[0].replace("\n", " ")
    defs = [
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")
    ]
    classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]

    imports: set[str] = set()
    local_pkg = src_root.name
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                rel = path.parent
                for _ in range(node.level - 1):
                    rel = rel.parent
                try:
                    prefix = ".".join(rel.relative_to(src_root).parts) if rel != src_root else ""
                except ValueError:
                    continue  # relative import in a file outside src_root
                base = f"{prefix}.{node.module}" if node.module and prefix else (node.module or prefix)
                imports.add(f"{local_pkg}.{base}" if base else local_pkg)
            elif node.module:
                imports.add(node.module)
    return Module(path=path, docstring=doc, defs=defs, classes=classes, imports=imports)


def module_name(path: Path, src_root: Path) -> str:
    rel = path.resolve().relative_to(src_root.resolve()).with_suffix("")
    return ".".join((src_root.name,) + rel.parts)


def build(bundle_path: Path, src_root: Path) -> dict[str, Any]:
    repo_root = bundle_path.parent.resolve()
    src_root = src_root.resolve()
    bundle, bases = load_bundle(bundle_path)
    tasks = extract_tasks(bundle, bases, repo_root)

    modules: dict[str, Module] = {}
    for py in sorted(src_root.rglob("*.py")):
        if any(p in {"__pycache__", ".venv"} for p in py.parts):
            continue
        modules[module_name(py, src_root)] = scan_module(py, src_root)

    # Imports may or may not carry the src package prefix, depending on whether
    # src/ is on sys.path at runtime. Both spellings must resolve, so index every
    # dotted suffix. Ambiguous suffixes are dropped rather than guessed.
    alias: dict[str, str] = {}
    ambiguous: set[str] = set()
    for full in modules:
        parts = full.split(".")
        for i in range(len(parts)):
            key = ".".join(parts[i:])
            if key in alias and alias[key] != full:
                ambiguous.add(key)
            alias[key] = full
    for key in ambiguous:
        alias.pop(key, None)

    def local_deps(name: str) -> set[str]:
        mod = modules.get(name)
        if not mod:
            return set()
        out = set()
        for imp in mod.imports:
            # `from pkg.mod import thing` gives pkg.mod; `import pkg.mod.thing`
            # may give a symbol path, so try the parent too.
            for cand in (imp, imp.rsplit(".", 1)[0]):
                target = alias.get(cand)
                if target and target != name:
                    out.add(target)
                    break
        return out

    # transitive closure per task entrypoint. Entrypoints OUTSIDE src (notebook
    # folders are the norm in real repos) still import the src package — scan
    # their imports and seed the closure with every resolvable src module.
    task_modules: dict[str, set[str]] = {}
    for t in tasks:
        if not t.entrypoint:
            continue
        try:
            seeds = [module_name(t.entrypoint, src_root)]
        except ValueError:
            facts = scan_module(t.entrypoint, src_root)
            seeds = []
            for imp in sorted(facts.imports):
                for cand in (imp, imp.rsplit(".", 1)[0]):
                    target = alias.get(cand)
                    if target and target not in seeds:
                        seeds.append(target)
                        break
        seen, stack = set(), list(seeds)
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(local_deps(cur) - seen)
        task_modules[f"{t.job}.{t.key}"] = seen

    used_by: dict[str, list[str]] = defaultdict(list)
    for tid, mods in task_modules.items():
        for m in mods:
            used_by[m].append(tid)

    orphans = sorted(m for m in modules if not used_by.get(m) and not m.endswith("__init__"))

    return {
        "bundle": bundle.get("bundle", {}).get("name", bundle_path.stem),
        "tasks": [
            {
                "id": f"{t.job}.{t.key}",
                "job": t.job,
                "task_key": t.key,
                "kind": t.kind,
                "target": t.target,
                "entrypoint": _rel(t.entrypoint, repo_root) if t.entrypoint else None,
                "depends_on": t.depends_on,
                "note": t.note,
                "modules": sorted(task_modules.get(f"{t.job}.{t.key}", set())),
            }
            for t in tasks
        ],
        "modules": {
            name: {
                "path": _rel(m.path, repo_root),
                "summary": m.docstring,
                "functions": m.defs,
                "classes": m.classes,
                "used_by": sorted(used_by.get(name, [])),
                "depends_on": sorted(local_deps(name)),
            }
            for name, m in sorted(modules.items())
        },
        "orphans": orphans,
        "unresolved": [f"{t.job}.{t.key}: {t.note}" for t in tasks if t.note],
    }


# --------------------------------------------------------------------------
# markdown
# --------------------------------------------------------------------------

def render(rm: dict[str, Any]) -> dict[str, str]:
    pages: dict[str, str] = {}

    lines = [f"# {rm['bundle']} — repo map", ""]
    lines.append("Generated. Do not hand-edit; edit the bundle or the code.")
    lines.append("")
    lines.append("## Tasks")
    lines.append("")
    lines.append("| task | entrypoint | depends on |")
    lines.append("|---|---|---|")
    for t in rm["tasks"]:
        entry = f"`{t['entrypoint']}`" if t["entrypoint"] else f"_{t['note'] or t['kind']}_"
        lines.append(f"| `{t['id']}` | {entry} | {', '.join(t['depends_on']) or '—'} |")

    groups: dict[str, list[str]] = defaultdict(list)
    for name in rm["modules"]:
        parts = name.split(".")
        groups[parts[1] if len(parts) > 2 else "(root)"].append(name)

    lines += ["", "## Shared modules", ""]
    for group, names in sorted(groups.items()):
        lines.append(f"### `{group}/`")
        lines.append("")
        for n in sorted(names):
            m = rm["modules"][n]
            api = ", ".join(f"`{d}()`" for d in m["functions"][:6]) or "—"
            lines.append(f"- **`{n}`** — {m['summary'] or '_no docstring_'}")
            lines.append(f"  - exports: {api}")
            lines.append(f"  - used by {len(m['used_by'])} task(s)")
        lines.append("")

    if rm["orphans"]:
        lines += ["## Unused by any task", ""]
        lines += [f"- `{o}`" for o in rm["orphans"]]
        lines.append("")
    if rm["unresolved"]:
        lines += ["## Unresolved", ""]
        lines += [f"- {u}" for u in rm["unresolved"]]
        lines.append("")
    pages["README.md"] = "\n".join(lines)

    for name, m in rm["modules"].items():
        p = [f"# `{name}`", "", f"`{m['path']}`", "", m["summary"] or "_No module docstring._", ""]
        if m["classes"]:
            p += ["## Classes", ""] + [f"- `{c}`" for c in m["classes"]] + [""]
        if m["functions"]:
            p += ["## Public functions", ""] + [f"- `{f}()`" for f in m["functions"]] + [""]
        p += ["## Used by", ""]
        p += [f"- `{u}`" for u in m["used_by"]] or ["_No task reaches this module._"]
        p += ["", "## Depends on", ""]
        p += [f"- `{d}`" for d in m["depends_on"]] or ["_No local dependencies._"]
        pages[f"modules/{name}.md"] = "\n".join(p) + "\n"

    return pages


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a repo map from a Databricks Asset Bundle")
    ap.add_argument("--bundle", type=Path, default=Path("databricks.yml"))
    ap.add_argument("--src", type=Path, default=Path("src"))
    ap.add_argument("--out", type=Path, help="write markdown wiki here")
    ap.add_argument("--json", type=Path, help="write repo map JSON here")
    args = ap.parse_args()

    rm = build(args.bundle, args.src)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rm, indent=2), encoding="utf-8")
    if args.out:
        for rel, body in render(rm).items():
            dest = args.out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body, encoding="utf-8")

    resolved = sum(1 for t in rm["tasks"] if t["entrypoint"])
    print(
        f"{len(rm['tasks'])} tasks ({resolved} resolved), "
        f"{len(rm['modules'])} modules, {len(rm['orphans'])} unused"
    )
    for u in rm["unresolved"]:
        print(f"  unresolved: {u}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
