"""Load, validate, and reason about the graph: section of tramat.yml.

Plugin-internal. Nothing in a user repo imports this module — it reads the
repo, it is not read by it. Accepts either a merged manifest (tramat.yml with
a top-level `graph:` key) or a bare graph file (steps at the top level).

    python3 scripts/graph.py tramat.yml
    python3 scripts/graph.py tramat.yml --strict
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

STAGES = ("planned", "implemented", "tested", "shipped")
AUX_KINDS = {"quarantine", "metrics", "checkpoint", "side_effect"}
VIA = {"declared", "observed", "inferred"}
STRATEGIES = {"overwrite_table", "overwrite_partition", "merge_on_key", "append_dedup", "none"}


@dataclass
class Finding:
    severity: str  # error | warn | info
    step: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity:5}] {self.step}: {self.message}"


@dataclass
class Step:
    raw: dict[str, Any]

    @property
    def id(self) -> str:
        return self.raw.get("id", "<unnamed>")

    @property
    def status(self) -> str:
        return self.raw.get("status", "planned")

    @property
    def reads(self) -> list[dict[str, Any]]:
        return self.raw.get("reads") or []

    @property
    def writes(self) -> list[dict[str, Any]]:
        return self.raw.get("writes") or []

    @property
    def primary_writes(self) -> list[dict[str, Any]]:
        return [w for w in self.writes if w.get("kind", "primary") == "primary"]

    @property
    def side_effects(self) -> list[str]:
        return self.raw.get("side_effects") or []

    @property
    def violates(self) -> bool:
        return bool(self.raw.get("violates_single_primary"))

    @property
    def retry_safe(self) -> bool:
        """Whether the loop may re-run this step in place.

        Requires an explicit human confirmation. Unset means unsafe: an agent
        reading a write mode cannot tell whether the partition scheme makes a
        retry safe, and a wrongly-retried append duplicates client data with
        nothing downstream erroring.
        """
        idem = self.raw.get("idempotency") or {}
        return bool(
            idem.get("safe")
            and idem.get("confirmed_by")
            and idem.get("confirmed_at")
            and not self.side_effects
        )

    @property
    def autonomous_eligible(self) -> bool:
        if self.raw.get("autonomous_eligible") is False:
            return False
        return not self.violates

    def validate(self) -> list[Finding]:
        f: list[Finding] = []
        sid = self.id

        if self.status not in STAGES:
            f.append(Finding("error", sid, f"unknown status {self.status!r}; expected {STAGES}"))

        n_primary = len(self.primary_writes)
        if n_primary == 0:
            f.append(Finding("error", sid, "no primary write; every step must produce one asset"))
        elif n_primary > 1 and not self.violates:
            refs = ", ".join(w["ref"] for w in self.primary_writes)
            f.append(
                Finding(
                    "error",
                    sid,
                    f"{n_primary} primary writes ({refs}) — the step spans waves. "
                    "Split it, or set violates_single_primary with a reason.",
                )
            )
        if self.violates and not self.raw.get("violation_reason"):
            f.append(Finding("error", sid, "violates_single_primary set without violation_reason"))

        idem = self.raw.get("idempotency") or {}
        strategy = idem.get("strategy", "none")
        if strategy not in STRATEGIES:
            f.append(Finding("error", sid, f"unknown idempotency strategy {strategy!r}"))
        if idem.get("safe") and strategy == "none":
            f.append(Finding("error", sid, "idempotency.safe requires a concrete strategy"))
        if strategy == "overwrite_partition" and not idem.get("partition_key"):
            f.append(Finding("error", sid, "overwrite_partition requires partition_key"))
        if strategy == "merge_on_key" and not idem.get("merge_key"):
            f.append(Finding("error", sid, "merge_on_key requires merge_key"))
        if idem.get("safe") and self.side_effects:
            f.append(
                Finding(
                    "error",
                    sid,
                    f"idempotency.safe with side_effects {self.side_effects}; "
                    "external writes cannot be replayed",
                )
            )
        if idem.get("safe") and not (idem.get("confirmed_by") and idem.get("confirmed_at")):
            f.append(
                Finding(
                    "error",
                    sid,
                    "idempotency.safe without confirmed_by/confirmed_at — "
                    "a safety claim nobody signed. Treated as unsafe; sign it or drop safe",
                )
            )
        if not self.retry_safe and not idem.get("safe") and not self.raw.get("recovery"):
            f.append(
                Finding(
                    "warn",
                    sid,
                    "not retry-safe and no recovery strategy declared; "
                    "a failure here halts rather than recovering",
                )
            )

        for r in self.reads:
            if r.get("via") not in VIA:
                f.append(Finding("error", sid, f"read {r.get('ref')} has via={r.get('via')!r}"))
            elif r["via"] == "inferred":
                f.append(
                    Finding(
                        "warn",
                        sid,
                        f"read {r['ref']} is inferred from code — wave order may be wrong",
                    )
                )
        for w in self.writes:
            kind = w.get("kind", "primary")
            if kind != "primary" and kind not in AUX_KINDS:
                f.append(Finding("error", sid, f"write {w.get('ref')} has unknown kind {kind!r}"))
            if w.get("via") not in VIA:
                f.append(Finding("error", sid, f"write {w.get('ref')} has via={w.get('via')!r}"))

        if self.status in ("tested", "shipped") and not self.raw.get("contract"):
            f.append(Finding("error", sid, f"status={self.status} with no contract reference"))
        if self.status == "shipped" and not self.raw.get("last_reconciled"):
            f.append(Finding("warn", sid, "shipped but never reconciled against UC lineage"))

        return f


@dataclass
class Graph:
    raw: dict[str, Any]
    section: dict[str, Any] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> Graph:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        # Merged manifest (tramat.yml, graph under `graph:`) or bare graph file.
        section = raw.get("graph") if isinstance(raw.get("graph"), dict) else raw
        return cls(raw=raw, section=section, steps=[Step(s) for s in (section.get("steps") or [])])

    def producer_of(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for s in self.steps:
            for w in s.primary_writes:
                ref = w.get("ref")
                if ref:
                    out[ref] = s.id
        return out

    def dependencies(self) -> dict[str, set[str]]:
        producer = self.producer_of()
        deps: dict[str, set[str]] = defaultdict(set)
        for s in self.steps:
            for r in s.reads:
                owner = producer.get(r.get("ref", ""))
                if owner and owner != s.id:
                    deps[s.id].add(owner)
        # explicit serialize blocks beat topology
        for grp in self.section.get("serialize") or []:
            members = [m for m in grp.get("steps", []) if m in {s.id for s in self.steps}]
            for earlier, later in zip(members, members[1:]):
                deps[later].add(earlier)
        return deps

    def waves(self) -> tuple[list[list[str]], set[str]]:
        deps = self.dependencies()
        remaining = {s.id for s in self.steps}
        waves: list[list[str]] = []
        while remaining:
            ready = sorted(n for n in remaining if not (deps.get(n, set()) & remaining))
            if not ready:
                return waves, remaining
            waves.append(ready)
            remaining -= set(ready)
        return waves, set()

    def next_step(self) -> Step | None:
        """The furthest-behind autonomous-eligible step whose deps are satisfied.

        This is the loop's pick. Dependencies must be shipped, not merely
        complete — a step is not ready to build on until its gate has passed
        in prod.
        """
        deps = self.dependencies()
        by_id = {s.id: s for s in self.steps}
        candidates = [
            s
            for s in self.steps
            if s.status in STAGES
            and s.status != "shipped"
            and s.autonomous_eligible
            and all(by_id[d].status == "shipped" for d in deps.get(s.id, set()) if d in by_id)
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda s: (STAGES.index(s.status), s.id))

    def validate(self) -> list[Finding]:
        findings: list[Finding] = []
        seen: dict[str, str] = {}
        step_ids = {s.id for s in self.steps}
        for s in self.steps:
            findings.extend(s.validate())
            for w in s.primary_writes:
                ref = w.get("ref")
                if not ref:
                    findings.append(Finding("error", s.id, "primary write with no ref"))
                    continue
                if ref in seen:
                    findings.append(
                        Finding("error", s.id, f"{ref} already produced by {seen[ref]}")
                    )
                seen[ref] = s.id

        # serialize groups must reference real steps — a silently dropped member
        # is false safety in the one place that overrides topology
        for grp in self.section.get("serialize") or []:
            for member in grp.get("steps", []):
                if member not in step_ids:
                    findings.append(
                        Finding(
                            "error",
                            "<graph>",
                            f"serialize references unknown step {member!r} — "
                            "the constraint it encodes is not being enforced",
                        )
                    )

        # a dependency satisfied by a single-primary VIOLATOR has no meaningful
        # graph position; wave placement downstream of it is a guess
        producer = self.producer_of()
        violators = {s.id for s in self.steps if s.violates}
        for s in self.steps:
            for r in s.reads:
                owner = producer.get(r.get("ref", ""))
                if owner in violators and owner != s.id:
                    findings.append(
                        Finding(
                            "warn",
                            s.id,
                            f"depends on {r.get('ref')} produced by {owner}, which violates "
                            "single-primary — this step's wave position is unreliable",
                        )
                    )

        _, cyclic = self.waves()
        if cyclic:
            findings.append(Finding("error", "<flow>", f"cycle among: {', '.join(sorted(cyclic))}"))

        producer = self.producer_of()
        for s in self.steps:
            for r in s.reads:
                if r.get("ref") not in producer:
                    findings.append(
                        Finding("info", s.id, f"reads external asset {r.get('ref')} (not in flow)")
                    )
        return findings

    def report(self) -> str:
        lines: list[str] = []
        waves, cyclic = self.waves()
        by_id = {s.id: s for s in self.steps}

        counts = defaultdict(int)
        for s in self.steps:
            counts[s.status] += 1
        lines.append(
            "  ".join(f"{st}: {counts[st]}" for st in STAGES)
            + f"   ({len(self.steps)} steps)"
        )
        lines.append("")

        for i, wave in enumerate(waves, 1):
            lines.append(f"wave {i}")
            for sid in wave:
                s = by_id[sid]
                marks = []
                if not s.retry_safe:
                    marks.append("no-retry")
                if s.violates:
                    marks.append("VIOLATES")
                if not s.autonomous_eligible:
                    marks.append("manual")
                if any(r.get("via") == "inferred" for r in s.reads):
                    marks.append("inferred-edge")
                suffix = f"  [{', '.join(marks)}]" if marks else ""
                lines.append(f"  {s.status:12} {sid}{suffix}")
        if cyclic:
            lines.append(f"\nUNPLACEABLE (cycle): {', '.join(sorted(cyclic))}")

        nxt = self.next_step()
        lines.append("")
        if nxt:
            target = STAGES[STAGES.index(nxt.status) + 1]
            lines.append(f"next: {nxt.id}  {nxt.status} -> {target}")
        else:
            blocked = [s.id for s in self.steps if s.status != "shipped"]
            lines.append(
                "next: none — all shipped"
                if not blocked
                else f"next: none — blocked or manual: {', '.join(blocked)}"
            )
        return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate and report on the tramat.yml graph section")
    ap.add_argument("path", type=Path, nargs="?", default=Path("tramat.yml"))
    ap.add_argument("--strict", action="store_true", help="exit non-zero on any error finding")
    args = ap.parse_args()

    graph = Graph.load(args.path)
    findings = graph.validate()
    # validate first: report() assumes statuses/refs are well-formed, and a
    # malformed manifest should produce findings, not a traceback
    if not any(f.severity == "error" for f in findings):
        print(graph.report())
    if findings:
        print()
        for sev in ("error", "warn", "info"):
            for f in [x for x in findings if x.severity == sev]:
                print(str(f), file=sys.stderr if sev == "error" else sys.stdout)

    n_err = sum(1 for f in findings if f.severity == "error")
    return 1 if (args.strict and n_err) else 0


if __name__ == "__main__":
    raise SystemExit(main())
