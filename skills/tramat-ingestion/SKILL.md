---
name: tramat-ingestion
description: The canonical tramat shape for ingesting an external source into Databricks — fetch task → landing Volume → Auto Loader bronze → silver via Lakeflow Spark Declarative Pipelines — plus the decision table for when NOT to use SDP. Read before adding or modifying any source ingestion in a tramat repo.
---

# tramat-ingestion

The canonical shape for a new API/file source. Recommended, never insisted — record deviations in `tramat.yml`.

## The shape: fetch and pipeline are separate

```
fetch job task (python wheel, serverless)      SDP pipeline (serverless)
  API/scraper → JSONL files in landing   →    Auto Loader → <entity>_bronze → <entity>_silver
  /Volumes/{catalog}/{source}/landing/{entity}/dt=YYYY-MM-DD/run=…/
```

The split is the point: the messy, imperative, external-world half (auth, retries, rate limits, proxies) lives in a **job task** where failure is loud and retryable; the declarative half (schema, dedup, typing, expectations) lives in **SDP** where the engine owns incremental processing. Never fetch inside a pipeline; never parse/clean inside the fetcher.

Rules:

- **Naming** (standard mode): schema = source; tables `<entity>_bronze` / `<entity>_silver` in that schema; landing files under `conventions.naming.landing_volume` with `dt=`/`run=` partnering directories so Auto Loader ingests incrementally and reruns don't collide.
- **Fetch short-circuits**: hash-compare against what's already stored (`hashing.py` helpers) and write only new/changed records; when nothing is new, `qa.signal_skip()` so downstream tasks skip instead of burning compute. Every fetch task carries a `timeout_seconds` **hang-guard** — external calls hang (observed: a 33h stuck scrape); the timeout is a guard, not a runtime budget, so size it generously per target.
- **Bronze is raw**: permissive schema (rescue data on), no business logic. Silver is typed, deduplicated on the natural key, expectation-guarded. Business aggregation is gold (tramat-modeling, later).
- **Mechanics defer to the official skills**: `databricks-pipelines` for SDP API/syntax, `databricks-jobs` for job/task config, `databricks-lakeflow-connect` when the source is a supported SaaS/DB connector — check that FIRST: a managed connector beats a hand-rolled fetcher.
- **Every new source is declared in `tramat.yml` `graph:`** — step for the fetch+pipeline, writes with `via: declared`, `side_effects: [external_http]` on the fetch, and idempotency **proposed by you but signed only by the user** (tramat-core Rule 3).

## When NOT SDP

| Situation | Do instead |
|---|---|
| Source is a Lakeflow Connect-supported SaaS/DB (Salesforce, SQL Server, Postgres CDC, …) | Managed connector via `databricks-lakeflow-connect`; no fetcher at all |
| Write target needs a library unavailable on serverless (e.g. Snowflake Spark connector) | Jobs task on a classic profile (see `tramat-compute`) |
| Long-running scraper needing spot config / custom instance control | Fetch stays a jobs task (it already is); assign a classic profile with a recorded reason |
| One-shot backfill / manual load | Plain job task writing Delta via `delta.py` helpers; no pipeline ceremony |
| Sub-second latency streaming | Not v0.1 tramat territory; see `databricks-spark-structured-streaming` |

The fetch/pipeline split already absorbs most "SDP can't do X" cases — X usually belongs in the fetcher.

## References (load on demand)

- `references/fetch-task.md` — worked fetch task: widgets, incremental key, hash short-circuit, landing layout, skip signal.
- `references/sdp-pipeline.md` — worked `pipelines/<source>/bronze_silver.py`: Auto Loader bronze, silver dedup + expectations.
- `references/resources-job.md` — worked `resources/<source>.yml`: pipeline + job (fetch → pipeline_task), serverless wiring, hang-guards, tags.
