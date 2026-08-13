"""PostToolUse hook: warn (never block) when an enforced-tier file is edited.

Enforced-tier files are rendered by tramat's renderer and re-diffed by doctor;
a hand edit is not forbidden, but it will surface as drift. This hook makes
that consequence visible at edit time instead of at the next doctor run.

Reads .tramat/applied.json (written by render.py, M3+):

    {"files": {"<repo-relative-path>": {"tier": "enforced" | "seeded" | "merged", ...}}}

No applied.json, or the file isn't tracked, or anything goes wrong: silent
exit 0. The tool call has already run; this hook only adds context.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    payload = json.load(sys.stdin)
    file_path = (payload.get("tool_input") or {}).get("file_path")
    cwd = Path(payload.get("cwd") or Path.cwd())
    if not file_path:
        return

    applied_path = cwd / ".tramat" / "applied.json"
    if not applied_path.exists():
        return
    applied = json.loads(applied_path.read_text(encoding="utf-8"))
    files = applied.get("files") or {}

    try:
        rel = str(Path(file_path).resolve().relative_to(cwd.resolve()))
    except ValueError:
        return
    entry = files.get(rel)
    if not entry or entry.get("tier") != "enforced":
        return

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        f"tramat: {rel} is an ENFORCED-tier rendered file "
                        f"(template {entry.get('template', '?')}). Hand edits here are "
                        "reported as drift by /tramat:doctor, which re-renders and diffs it. "
                        "If the change is intentional, adopt it into an override in tramat.yml "
                        "instead of editing the rendered output."
                    ),
                }
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # advisory only; never interfere with the edit
    sys.exit(0)
