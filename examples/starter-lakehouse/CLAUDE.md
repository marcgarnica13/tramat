# starter-lakehouse

Databricks lakehouse repo managed with [tramat](https://github.com/marcgarnica13/tramat). Rules for agents working here:

## Read tramat.yml first

`tramat.yml` is the source of truth: `conventions:` (naming, layout, compute) are this repo's choices — never re-derive or contradict them; `graph:` is the data graph — trust it over your reading of the code or the DAB task order. Every read/write edge carries `via:` provenance; `idempotency.safe: true` counts only when signed (`confirmed_by` + `confirmed_at`). Never retry a step that isn't signed retry-safe.

## Ownership

Every file in this repo is project-owned — edit freely. When you change a convention (naming, layout, compute, targets), record the change in `tramat.yml` so the manifest stays true; `/tramat:doctor` checks the repo against it and reports gaps as advisories.

## Layout

- `src/starter_lakehouse/` — shared helpers (env, delta, merge, hashing, qa). Check here before writing a new helper.
- `pipelines/` — Lakeflow Spark Declarative Pipelines source.
- `resources/` — DAB job/pipeline definitions, one YAML per source/domain.
- `contracts/` — per-asset ODCS data contracts.
- Naming: catalog = environment, schema = source/domain, layer as table suffix (`players_bronze`/`_silver`/`_gold`; `dim_*`/`fct_*` in gold).

## Verify (Tier 0 — run before claiming anything works)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest
databricks bundle validate
```

Deploying or running anything in a workspace (Tier 1) happens only on the user's explicit request.
