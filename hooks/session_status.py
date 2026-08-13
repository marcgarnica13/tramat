"""SessionStart hook: orient the agent, never slow it down.

Budget: <1s, no network, no subprocesses. Reads tramat.yml if present and
prints a status line plus the next eligible step — the agent starts oriented,
not blank. Prints nothing in repos that have neither tramat.yml nor
databricks.yml. Always exits 0: a broken hook must never break a session.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        payload = {}
    cwd = Path(payload.get("cwd") or Path.cwd())

    manifest = cwd / "tramat.yml"
    if not manifest.exists():
        if (cwd / "databricks.yml").exists():
            print(
                "tramat: Databricks bundle repo without tramat.yml — "
                "/tramat:onboard surveys conventions and creates one; /tramat:doctor checks the environment."
            )
        return

    try:
        import yaml  # noqa: F401
    except ImportError:
        print("tramat: tramat.yml present but PyYAML is missing — run /tramat:doctor")
        return

    scripts = Path(__file__).resolve().parent.parent / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        import graph as graph_mod

        g = graph_mod.Graph.load(manifest)
    except Exception as e:
        print(f"tramat: tramat.yml present but unreadable ({e}) — run /tramat:doctor")
        return

    if not g.steps:
        print("tramat: manifest present, graph empty — steps land as work is scaffolded.")
        return

    findings = g.validate()
    n_err = sum(1 for f in findings if f.severity == "error")
    counts: dict[str, int] = {}
    for s in g.steps:
        counts[s.status] = counts.get(s.status, 0) + 1
    status = "  ".join(f"{k}: {v}" for k, v in counts.items())

    lines = [f"tramat: {len(g.steps)} steps ({status})"]
    if n_err:
        lines.append(
            f"tramat: manifest has {n_err} validation error(s) — "
            "run `python3 scripts/graph.py tramat.yml` via /tramat:doctor before building on it"
        )
    else:
        nxt = g.next_step()
        if nxt:
            target = graph_mod.STAGES[graph_mod.STAGES.index(nxt.status) + 1]
            lines.append(f"tramat: next eligible step — {nxt.id} ({nxt.status} -> {target})")
    print("\n".join(lines))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never break a session start
    sys.exit(0)
