# Agent instructions — starter-lakehouse

This repo is managed with [tramat](https://github.com/marcgarnica13/tramat). These rules apply to any coding agent (Claude Code, Codex, or other).

1. **Read `tramat.yml` first.** `conventions:` are this repo's recorded choices — follow them, don't re-derive. `graph:` is the authoritative data graph: what each step reads/writes, with `via:` provenance on every edge, and signed idempotency (`confirmed_by`/`confirmed_at`) before any retry is safe. Trust it over code-reading and over the DAB task order.
2. **Everything is project-owned.** Edit any file freely; when a change alters a convention, record it in `tramat.yml` so the manifest stays true. `/tramat:doctor` reports convention gaps as advisories.
3. **Reuse before writing.** Shared helpers live in `src/starter_lakehouse/` (env, delta, merge, hashing, qa). Extend them rather than duplicating logic in pipelines.
4. **Naming:** catalog = environment, schema = source/domain, layer as table suffix (`players_bronze`/`_silver`/`_gold`; `dim_*`/`fct_*` in gold).
5. **Verify Tier 0 before claiming done:** `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest`, `databricks bundle validate`. Never deploy or run workspace jobs unless the user explicitly asks (Tier 1).
6. **Incidents** are logged in `docs/runbook.md`, not as comment archaeology in YAML.
