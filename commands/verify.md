---
description: Run tramat's verification gates — Tier 0 static gates always (ruff, format, mypy, pytest, bundle validate, doctor, graph); with an explicit "full"/"tier 1" request, a dev deploy + sample run via the dev-runner agent.
---

Verify this repo per the `tramat-verify` skill.

## Tier 0 (default — always this unless told otherwise)

Run the full static gate from the skill: ruff check, ruff format --check, mypy src, pytest, `databricks bundle validate` (ask which profile — never pick one), `doctor.py --repo-only .`, and `graph.py tramat.yml` when the graph has steps. Report gate → pass/fail, failures first, terse. Fix-or-report-red; never narrate around a failure.

## Tier 1 (only when `$ARGUMENTS` contains `--full`/`tier 1` or the user explicitly asked this turn)

1. Confirm with the user: which job/pipeline, which auth profile, and the **sample scope** (the bounding parameter and its value). Refuse unbounded runs — if no sample-scope parameter exists, add one first.
2. Spawn the `dev-runner` agent with: repo path, profile, target `dev`, the job/pipeline name, sample parameters, and the tables it is expected to write (from the `graph:` step).
3. Relay dev-runner's report: deploy result, run result + duration, row counts/QA on expected tables, anything unexpected. Offer cleanup (destroy or drop sample outputs) — don't do it unasked.
4. On a green Tier-1 run, propose updating the graph step's `status` to `tested` (and remind about unsigned idempotency if still unsigned).

Never escalate Tier 0 → Tier 1 on your own judgment; cost and blast radius are the user's call. Reuse review (reuse-reviewer on the diff) joins this command in a later milestone.
