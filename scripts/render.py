"""THE tramat renderer: template substitution + applied.json bookkeeping.

Plugin-internal, stdlib-only. Every file tramat generates goes through this
script — never ad-hoc sed, never inline heredocs. That single funnel is what
makes governance tiers real: each rendered file is recorded in
`.tramat/applied.json` with its tier, template id, template version, the
variables it was rendered with, and a sha256 of the rendered content — enough
for `check` (and doctor) to re-render enforced files later and report drift.

    python3 scripts/render.py list                     # template groups + files
    python3 scripts/render.py vars repo                # variables a group needs
    python3 scripts/render.py apply repo --dest DIR --var project_name=acme ...
    python3 scripts/render.py check [--dest DIR]       # drift report, exit 1 on drift

Template language (deliberately tiny, no conditionals, no loops):
  {{tramat.<var>}}   substituted; unknown or missing vars are errors.
Anything else — including Databricks' own `{{job.run_id}}` and `${var.x}` —
passes through untouched.

Tiers at apply time: `enforced` refuses to overwrite an existing file without
--force; `seeded` and `merged` are generated once and silently skipped if the
file already exists (they are project-owned after first render).

applied.json shape (read by hooks/enforced_guard.py and doctor):

    {"renderer": "...", "files": {"<repo-relative-path>": {
        "tier": "enforced|seeded|merged", "template": "<group>/<name>",
        "version": "<group version>", "sha256": "...", "vars": {...},
        "rendered_at": "..."}}}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

RENDERER_VERSION = "0.1.0"
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PLUGIN_ROOT / "templates"
APPLIED_REL = Path(".tramat") / "applied.json"

PLACEHOLDER = re.compile(r"\{\{tramat\.([a-z0-9_]+)\}\}")
# Anything that still looks like a tramat placeholder after substitution is a
# bug (typo'd var name, bad casing) — catch it, don't ship it.
LEFTOVER = re.compile(r"\{\{tramat\.[^}]*\}\}")

TIERS = ("enforced", "seeded", "merged")


class RenderError(Exception):
    pass


# ---------- template groups ----------


def load_group(group: str) -> dict:
    manifest_path = TEMPLATES_DIR / group / "template.json"
    if not manifest_path.exists():
        available = ", ".join(sorted(p.parent.name for p in TEMPLATES_DIR.glob("*/template.json")))
        raise RenderError(f"unknown template group {group!r} (available: {available or 'none'})")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest.get("files", []):
        for key in ("src", "target", "tier"):
            if key not in entry:
                raise RenderError(f"{group}/template.json: file entry missing {key!r}: {entry}")
        if entry["tier"] not in TIERS:
            raise RenderError(f"{group}/template.json: bad tier {entry['tier']!r} for {entry['target']}")
        src = TEMPLATES_DIR / group / entry["src"]
        if not src.exists():
            raise RenderError(f"{group}/template.json: src not found: {entry['src']}")
    return manifest


def group_vars(group: str) -> set[str]:
    """All variables referenced by a group's file bodies and target paths."""
    manifest = load_group(group)
    needed: set[str] = set()
    for entry in manifest.get("files", []):
        text = (TEMPLATES_DIR / group / entry["src"]).read_text(encoding="utf-8")
        needed.update(PLACEHOLDER.findall(text))
        needed.update(PLACEHOLDER.findall(entry["target"]))
    return needed


# ---------- rendering ----------


def substitute(text: str, variables: dict[str, str], context: str) -> str:
    def repl(m: re.Match) -> str:
        name = m.group(1)
        if name not in variables:
            raise RenderError(f"{context}: missing variable {name!r}")
        return str(variables[name])

    out = PLACEHOLDER.sub(repl, text)
    leftover = LEFTOVER.search(out)
    if leftover:
        raise RenderError(f"{context}: unrendered placeholder {leftover.group(0)!r}")
    return out


def render_file(group: str, entry: dict, variables: dict[str, str]) -> tuple[str, str]:
    """Return (relative target path, rendered content) for one template entry."""
    src = TEMPLATES_DIR / group / entry["src"]
    target = substitute(entry["target"], variables, f"{group}/{entry['src']} (target path)")
    tpath = Path(target)
    if tpath.is_absolute() or ".." in tpath.parts:
        raise RenderError(f"{group}/{entry['src']}: unsafe target path {target!r}")
    content = substitute(src.read_text(encoding="utf-8"), variables, f"{group}/{entry['src']}")
    return target, content


def used_vars(group: str, entry: dict) -> dict[str, str]:
    """Names referenced by one entry (body + target), for applied.json."""
    text = (TEMPLATES_DIR / group / entry["src"]).read_text(encoding="utf-8")
    return sorted(set(PLACEHOLDER.findall(text)) | set(PLACEHOLDER.findall(entry["target"])))


def sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def template_id(group: str, entry: dict) -> str:
    return f"{group}/{entry['src'].removesuffix('.tmpl')}"


# ---------- applied.json ----------


def load_applied(dest: Path) -> dict:
    path = dest / APPLIED_REL
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"renderer": RENDERER_VERSION, "files": {}}


def save_applied(dest: Path, applied: dict) -> None:
    applied["renderer"] = RENDERER_VERSION
    applied["files"] = dict(sorted(applied["files"].items()))
    path = dest / APPLIED_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(applied, indent=2, sort_keys=False) + "\n", encoding="utf-8")


# ---------- commands ----------


def cmd_apply(group: str, dest: Path, variables: dict[str, str], force: bool) -> list[dict]:
    manifest = load_group(group)
    needed = group_vars(group)
    missing = sorted(needed - set(variables))
    if missing:
        raise RenderError(
            f"group {group!r} needs variables not provided: {', '.join(missing)} "
            f"(pass each as --var name=value)"
        )
    unknown = sorted(set(variables) - needed)
    if unknown:
        raise RenderError(f"variables not used by group {group!r}: {', '.join(unknown)}")

    # Render everything first: no partial writes on error.
    rendered: list[tuple[dict, str, str]] = []
    for entry in manifest["files"]:
        target, content = render_file(group, entry, variables)
        rendered.append((entry, target, content))

    applied = load_applied(dest)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results = []
    for entry, target, content in rendered:
        out = dest / target
        if out.exists():
            if entry["tier"] in ("seeded", "merged"):
                results.append({"target": target, "tier": entry["tier"], "action": "kept"})
                continue
            if not force:
                raise RenderError(
                    f"{target} exists and is enforced-tier; re-render requires --force"
                )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        applied["files"][target] = {
            "tier": entry["tier"],
            "template": template_id(group, entry),
            "group": group,
            "src": entry["src"],
            "version": manifest.get("version", "0"),
            "sha256": sha256(content),
            "vars": {name: str(variables[name]) for name in used_vars(group, entry)},
            "rendered_at": now,
        }
        results.append({"target": target, "tier": entry["tier"], "action": "rendered"})
    save_applied(dest, applied)
    return results


def cmd_check(dest: Path) -> list[dict]:
    """Drift report for enforced-tier files recorded in applied.json."""
    path = dest / APPLIED_REL
    if not path.exists():
        raise RenderError(f"no {APPLIED_REL} under {dest} — nothing was rendered here")
    applied = json.loads(path.read_text(encoding="utf-8"))
    findings = []
    for target, entry in (applied.get("files") or {}).items():
        if entry.get("tier") != "enforced":
            continue
        finding = {"target": target, "template": entry.get("template", "?"), "status": "ok", "detail": ""}
        findings.append(finding)
        on_disk = dest / target
        if not on_disk.exists():
            finding.update(status="missing", detail="enforced file deleted; re-render or remove from applied.json")
            continue
        group, src = entry.get("group"), entry.get("src")
        src_path = TEMPLATES_DIR / (group or "") / (src or "")
        if not group or not src or not src_path.exists():
            finding.update(status="unknown-template", detail="template no longer in this plugin version")
            continue
        try:
            manifest = load_group(group)
            file_entry = next(e for e in manifest["files"] if e["src"] == src)
            _, fresh = render_file(group, file_entry, entry.get("vars") or {})
        except (RenderError, StopIteration) as e:
            finding.update(status="unknown-template", detail=str(e))
            continue
        disk_sha = sha256(on_disk.read_text(encoding="utf-8"))
        if disk_sha == sha256(fresh):
            if manifest.get("version", "0") != entry.get("version"):
                finding.update(
                    status="ok",
                    detail=f"template version {entry.get('version')} → {manifest.get('version')} (content unchanged)",
                )
            continue
        if disk_sha == entry.get("sha256"):
            finding.update(
                status="template-updated",
                detail=f"template changed upstream ({entry.get('version')} → {manifest.get('version', '0')}); "
                "re-render with --force to adopt",
            )
        else:
            finding.update(
                status="edited",
                detail="hand-edited since render; revert, re-render, or adopt into a tramat.yml override",
            )
    return findings


def cmd_list() -> list[dict]:
    groups = []
    for manifest_path in sorted(TEMPLATES_DIR.glob("*/template.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        groups.append(
            {
                "group": manifest_path.parent.name,
                "version": manifest.get("version", "0"),
                "description": manifest.get("description", ""),
                "files": [{"target": e["target"], "tier": e["tier"]} for e in manifest.get("files", [])],
            }
        )
    return groups


# ---------- CLI ----------


def parse_vars(pairs: list[str]) -> dict[str, str]:
    variables = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not name:
            raise RenderError(f"--var expects name=value, got {pair!r}")
        variables[name] = value
    return variables


def main() -> int:
    ap = argparse.ArgumentParser(description="tramat template renderer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="template groups and their files")

    ap_vars = sub.add_parser("vars", help="variables a group requires")
    ap_vars.add_argument("group")

    ap_apply = sub.add_parser("apply", help="render a group into a repo")
    ap_apply.add_argument("group")
    ap_apply.add_argument("--dest", type=Path, required=True)
    ap_apply.add_argument("--var", action="append", default=[], metavar="name=value")
    ap_apply.add_argument("--force", action="store_true", help="overwrite existing enforced-tier files")
    ap_apply.add_argument("--json", action="store_true")

    ap_check = sub.add_parser("check", help="drift report for enforced files")
    ap_check.add_argument("--dest", type=Path, default=Path.cwd())
    ap_check.add_argument("--json", action="store_true")

    args = ap.parse_args()
    try:
        if args.cmd == "list":
            for g in cmd_list():
                print(f"{g['group']} v{g['version']} — {g['description']}")
                for f in g["files"]:
                    print(f"  [{f['tier'][0].upper()}] {f['target']}")
            return 0
        if args.cmd == "vars":
            for name in sorted(group_vars(args.group)):
                print(name)
            return 0
        if args.cmd == "apply":
            results = cmd_apply(args.group, args.dest.resolve(), parse_vars(args.var), args.force)
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                for r in results:
                    print(f"{r['action']:<9} [{r['tier'][0].upper()}] {r['target']}")
            return 0
        if args.cmd == "check":
            findings = cmd_check(args.dest.resolve())
            drift = [f for f in findings if f["status"] in ("edited", "missing")]
            if args.json:
                print(json.dumps({"ok": not drift, "files": findings}, indent=2))
            else:
                for f in findings:
                    mark = "✓" if f["status"] == "ok" else "✗" if f["status"] in ("edited", "missing") else "!"
                    line = f"{mark} {f['target']} ({f['status']})"
                    if f["detail"]:
                        line += f" — {f['detail']}"
                    print(line)
                print(f"\n{len(drift)} drifted of {len(findings)} enforced file(s)")
            return 1 if drift else 0
    except RenderError as e:
        print(f"render error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
