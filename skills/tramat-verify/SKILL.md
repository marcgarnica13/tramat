---
name: tramat-verify
description: The verification protocol for tramat repos — Tier 0 (static gates, always) and Tier 1 (dev deploy + sample run, only on explicit user request, via the dev-runner agent). Read before claiming any data-engineering change works, and before any workspace deploy or run.
---

# tramat-verify

Two tiers. Tier 0 is unconditional; Tier 1 **never runs without the user explicitly asking for it in this conversation** — not "would be nice", not inferred. No auto-escalation, ever.

## Tier 0 — static gates (always, before claiming done)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest
databricks bundle validate            # needs auth: user picks the profile, never you
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --repo-only .
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/graph.py" tramat.yml   # when graph: has steps
```

Rules:

- Run all of it even when "only YAML changed" — validate is the only gate that sees YAML, and validate ≠ deploy (terraform rejects things validate passes; treat a green validate as necessary, not sufficient).
- A red gate is fixed before reporting, or reported as red — never narrated around.
- Report tersely: gate → pass/fail, failures first, no logs dumped into context.

## Tier 1 — dev deploy + sample run (explicit request only)

What it is: deploy the bundle to the **dev** target, run the affected job/pipeline with a **sample-scoped** configuration, quick-QA the outputs, report. Cost and blast radius are real; that's why it's opt-in per invocation.

- **Delegate to the `dev-runner` agent** — the deploy/poll/QA loop is long-output work that does not belong in main context (tramat-core token economy).
- The user picks the auth profile. Never auto-select one.
- Sample scope is mandatory: a Tier-1 run fetches/processes a bounded slice (one competition, one day, `LIMIT`ed source), not the full workload. If the job has no sample-scope parameter, add one before running.
- Dev target only. Staging/prod deploys are not verification — they are releases, and they belong to the repo's CI, not to the harness (isolation and promotion are the repo CI's job; the harness is only aware).
- After the run: schema + row-count sanity on the written tables (`qa.py` thresholds), then report. Cleanup (`bundle destroy` or dropping sample outputs) is offered, not assumed.
- A Tier-1 pass updates the graph step's `status` (e.g. `implemented` → `tested`); a Tier-0-only change does not.
