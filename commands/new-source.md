---
description: Add a new external data source to a tramat repo — interview (auth, entities, incremental key, compute), then compose fetch task + SDP pipeline + resources YAML + tests from the ingestion references, declare the step in the graph, and verify Tier 0.
---

Add a new source to this repo the canonical tramat way. Requires a `tramat.yml` (no manifest → suggest `/tramat:init` or onboarding; do not proceed).

Skills to apply: `tramat-ingestion` (the shape + its `references/`), `tramat-compute` (compute assignment), `tramat-verify` (the gate). Compose files yourself from the references, adapted to this repo's recorded conventions — in `mode: adapted` repos the local conventions win over the canonical shape.

## 1. Pre-checks

- Read `tramat.yml`: naming scheme, landing volume pattern, layout dirs, compute defaults, existing graph steps.
- Reuse gate (light, deterministic): `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/repomap.py" --bundle databricks.yml --src src` — if a client/fetcher for this source or a near-duplicate helper already exists, surface it and ask before writing a second one.
- If the source is a Lakeflow Connect-supported SaaS/DB, stop and recommend the managed connector (`databricks-lakeflow-connect`) instead of a hand-rolled fetcher. Scaffold only if the user declines.

## 2. Interview (one round; never invent facts)

Take from `$ARGUMENTS` what's given; ask the rest:

- **Source name** (schema name) and **entities** to ingest first.
- **Auth**: scheme (token/OAuth/none) and where the secret lives (secret scope name — never a literal).
- **Incremental key**: which field marks new/changed records (or "full snapshot each run").
- **Compute**: serverless (default) — or, if the user names a constraint from the classic decision table, pick/define a `classic_profiles` entry **with its reason** in `tramat.yml`.
- **Sample scope** for dev runs: the parameter that bounds a test run (one competition, one day, a limit). This is mandatory — Tier 1 refuses unbounded runs.

## 3. Compose

Following the references (`fetch-task.md`, `sdp-pipeline.md`, `resources-job.md`), write:

- `src/<package>/sources/<source>/fetch.py` + `[project.scripts]` entry — fetch with hash short-circuit, watermark from bronze, skip signal, hang-guard timeout in the job spec.
- `pipelines/<source>/bronze_silver.py` — Auto Loader bronze → deduped, expectation-guarded silver, per entity.
- `resources/<source>.yml` — pipeline + job (fetch → pipeline_task), serverless or assigned classic profile, tags, `max_concurrent_runs: 1`, no schedule (schedules are prod-only, in `databricks.yml`).
- `tests/sources/test_<source>_fetch.py` — mocked API: happy path, empty, error, incremental vs full.

Then **declare the step** in `tramat.yml` `graph:`: `id: ingest_<source>`, `status: planned`, task/entrypoint, `writes:` for each bronze/silver table `via: declared`, `side_effects: [external_http]`, `reads: []`. Propose an `idempotency` block (strategy from the write mode) but leave `safe:` unsigned and **ask the user to sign it** (`confirmed_by`/`confirmed_at`) — never sign it yourself (tramat-core Rule 3).

## 4. Verify

Tier 0 per `tramat-verify` (ruff, format, mypy, pytest, `bundle validate` with a user-chosen profile, doctor, `graph.py`). Fix red before reporting. Offer — do not start — a Tier-1 sample run via `/tramat:verify` if the user wants the source proven against the workspace.

## 5. Report

Terse: files written, graph step added (and that idempotency awaits the user's signature), gate results, and the exact command for a Tier-1 sample run.
