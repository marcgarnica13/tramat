"""Reconcile the tramat.yml graph against reality.

Three views of what a step reads and writes:

    graph (declared)  x  code (inferred)  x  UC lineage (observed)

Disagreements are the output. The one that matters most is an undeclared
write: that is precisely what surprises a retry.

    python3 scripts/reconcile.py tramat.yml --src src/
    python3 scripts/reconcile.py tramat.yml --src src/ --lineage lineage.json --strict
    python3 scripts/reconcile.py --inventory --src src/     # brownfield: no manifest needed
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from graph import Finding, Graph, Step  # noqa: E402

# Spark call sites that read or write a named table. Deliberately conservative:
# a missed call becomes a warning, a wrong guess becomes a false error, and
# false errors are what make people switch the check off.
READ_CALLS = {"table", "readStream", "load"}
WRITE_CALLS = {"saveAsTable", "insertInto", "toTable", "createOrReplace"}
WRITE_MODE_CALLS = {"mode", "outputMode"}

TABLE_RE = re.compile(r"^[A-Za-z_][\w]*\.[A-Za-z_][\w]*(\.[A-Za-z_][\w]*)?$")


@dataclass
class CodeFacts:
    """What static analysis thinks a file does. All of it low-confidence."""

    reads: set[str] = field(default_factory=set)
    writes: set[str] = field(default_factory=set)
    write_modes: set[str] = field(default_factory=set)
    dynamic_refs: int = 0  # f-strings and variables we could not resolve


def scan_file(path: Path) -> CodeFacts:
    facts = CodeFacts()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        print(f"warn: cannot parse {path}: {exc}", file=sys.stderr)
        return facts

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr

        if attr in WRITE_MODE_CALLS and node.args:
            mode = _const_str(node.args[0])
            if mode:
                facts.write_modes.add(mode)
            continue

        if attr not in READ_CALLS and attr not in WRITE_CALLS:
            continue

        ref = None
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            candidate = _const_str(arg)
            if candidate and TABLE_RE.match(candidate):
                ref = candidate
                break
        if ref is None:
            if node.args or node.keywords:
                facts.dynamic_refs += 1
            continue

        if attr in WRITE_CALLS:
            facts.writes.add(ref)
        else:
            facts.reads.add(ref)

    return facts


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _qualify(ref: str, catalog: str) -> str:
    """The graph uses schema.table with a default catalog; code often spells it out.

    Non-table refs (models:/name, volume paths) and refs with no default
    catalog pass through untouched — prefixing those fabricates invalid names.
    """
    if ":" in ref or "/" in ref or not catalog:
        return ref
    return ref if ref.count(".") == 2 else f"{catalog}.{ref}"


def reconcile(
    graph: Graph,
    src_root: Path,
    lineage: dict[str, dict[str, list[str]]] | None = None,
) -> list[Finding]:
    """lineage maps step id -> {"reads": [...], "writes": [...]} from UC."""
    catalog = (graph.section.get("defaults") or {}).get("catalog", "")
    findings: list[Finding] = []

    for step in graph.steps:
        entry = step.raw.get("entrypoint")
        if not entry:
            findings.append(Finding("warn", step.id, "no entrypoint; cannot reconcile against code"))
            continue

        path = src_root.parent / entry if not (src_root / entry).exists() else src_root / entry
        if not path.exists():
            path = Path(entry)
        if not path.exists():
            findings.append(Finding("error", step.id, f"entrypoint {entry} does not exist"))
            continue

        facts = scan_file(path)
        declared_reads = {_qualify(r["ref"], catalog) for r in step.reads if "ref" in r}
        declared_writes = {_qualify(w["ref"], catalog) for w in step.writes if "ref" in w}
        declared_primary = {_qualify(w["ref"], catalog) for w in step.primary_writes}

        code_reads = {_qualify(r, catalog) for r in facts.reads}
        code_writes = {_qualify(w, catalog) for w in facts.writes}

        findings.extend(
            _diff(step, "code", declared_reads, declared_writes, declared_primary, code_reads, code_writes)
        )

        if facts.dynamic_refs:
            findings.append(
                Finding(
                    "warn",
                    step.id,
                    f"{facts.dynamic_refs} table refs built dynamically; "
                    "static analysis is incomplete here — rely on UC lineage",
                )
            )

        findings.extend(_check_mode_drift(step, facts))

        if lineage and step.id in lineage:
            obs = lineage[step.id]
            obs_reads = {_qualify(r, catalog) for r in obs.get("reads", [])}
            obs_writes = {_qualify(w, catalog) for w in obs.get("writes", [])}
            findings.extend(
                _diff(step, "lineage", declared_reads, declared_writes, declared_primary, obs_reads, obs_writes)
            )
        elif step.status == "shipped":
            findings.append(
                Finding("warn", step.id, "shipped but no UC lineage supplied; drift unverified")
            )

    findings.extend(_check_dab_disagreements(graph))
    return findings


def _diff(
    step: Step,
    source: str,
    declared_reads: set[str],
    declared_writes: set[str],
    declared_primary: set[str],
    actual_reads: set[str],
    actual_writes: set[str],
) -> list[Finding]:
    out: list[Finding] = []
    sev = "error" if source == "lineage" else "warn"

    for ref in sorted(actual_writes - declared_writes):
        out.append(
            Finding(
                "error",
                step.id,
                f"undeclared write to {ref} (per {source}) — "
                "an undeclared write is what breaks a retry",
            )
        )
    for ref in sorted(declared_writes - actual_writes):
        out.append(Finding("warn", step.id, f"declares write to {ref} but {source} shows none"))
    for ref in sorted(actual_reads - declared_reads):
        out.append(
            Finding(sev, step.id, f"undeclared read of {ref} (per {source}) — wave order may be wrong")
        )
    for ref in sorted(declared_reads - actual_reads):
        out.append(Finding("info", step.id, f"declares read of {ref} but {source} shows none"))
    return out


def _check_mode_drift(step: Step, facts: CodeFacts) -> list[Finding]:
    """A write-mode change invalidates a human's idempotency confirmation."""
    idem = step.raw.get("idempotency") or {}
    if not idem.get("confirmed_at"):
        return []
    strategy = idem.get("strategy")
    modes = facts.write_modes
    if not modes:
        return []

    expected = {
        "overwrite_table": {"overwrite"},
        "overwrite_partition": {"overwrite"},
        "merge_on_key": {"overwrite", "append", "update", "complete"},
        "append_dedup": {"append"},
    }.get(strategy or "", set())

    if expected and not (modes & expected):
        return [
            Finding(
                "error",
                step.id,
                f"write mode {sorted(modes)} does not match strategy {strategy!r} "
                f"confirmed on {idem['confirmed_at']} — idempotency confirmation is stale, "
                "re-confirm before the loop may retry this step",
            )
        ]
    return []


def _check_dab_disagreements(graph: Graph) -> list[Finding]:
    """Surface pre-recorded orchestration-vs-data disagreements as info."""
    return [
        Finding("info", d.get("ticket", "<graph>"), d.get("detail", "").strip())
        for d in (graph.section.get("known_disagreements") or [])
    ]


def inventory(src_root: Path) -> int:
    """Brownfield mode: no manifest. Report what the code actually touches.

    The seed for a graph: section — every static table read/write per file,
    plus a count of dynamic refs static analysis cannot resolve.
    """
    n_files = 0
    total = CodeFacts()
    for py in sorted(src_root.rglob("*.py")):
        if any(p in {"__pycache__", ".venv", "node_modules"} for p in py.parts):
            continue
        facts = scan_file(py)
        if not (facts.reads or facts.writes or facts.dynamic_refs):
            continue
        n_files += 1
        total.reads |= facts.reads
        total.writes |= facts.writes
        total.dynamic_refs += facts.dynamic_refs
        bits = []
        if facts.reads:
            bits.append("reads: " + ", ".join(sorted(facts.reads)))
        if facts.writes:
            bits.append("WRITES: " + ", ".join(sorted(facts.writes)))
        if facts.dynamic_refs:
            bits.append(f"dynamic refs: {facts.dynamic_refs}")
        print(f"{py}\n  " + "\n  ".join(bits))
    print(
        f"\n{n_files} files touch tables statically — "
        f"{len(total.reads)} distinct reads, {len(total.writes)} distinct writes, "
        f"{total.dynamic_refs} dynamic refs unresolved (rely on UC lineage for those)"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconcile the tramat.yml graph against code and UC lineage")
    ap.add_argument("path", type=Path, nargs="?", default=Path("tramat.yml"))
    ap.add_argument("--src", type=Path, default=Path("src"), help="source root")
    ap.add_argument("--lineage", type=Path, help="JSON: {step_id: {reads: [], writes: []}}")
    ap.add_argument("--inventory", action="store_true", help="no manifest: report what code touches")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    if args.inventory:
        return inventory(args.src)

    graph = Graph.load(args.path)
    lineage = json.loads(args.lineage.read_text()) if args.lineage else None
    findings = reconcile(graph, args.src, lineage)

    for sev in ("error", "warn", "info"):
        for f in [x for x in findings if x.severity == sev]:
            print(str(f), file=sys.stderr if sev == "error" else sys.stdout)

    n_err = sum(1 for f in findings if f.severity == "error")
    print(f"\n{n_err} errors, {sum(1 for f in findings if f.severity == 'warn')} warnings")
    return 1 if (args.strict and n_err) else 0


if __name__ == "__main__":
    raise SystemExit(main())
