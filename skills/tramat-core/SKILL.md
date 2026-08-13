---
name: tramat-core
description: Core operating rules for any repo with a tramat.yml manifest (or a Databricks bundle repo adopting tramat). Read this before writing or planning any pipeline, ingestion, transform, or ML code in such a repo — it defines the manifest as the source of truth, edge provenance, signed idempotency, governance tiers, naming, and the token-economy rules for the whole harness.
---

# tramat-core

Tramat is a harness for data engineering on Databricks. Its premise: agents fail on data work not from lack of skill but from lack of *artifacts they can't lie to*. This skill defines those artifacts and the rules for working with them.

**Stance (overrides everything below):** the harness helps; it never insists. Recommend state-of-the-art defaults, comply when the user chooses otherwise, and record the choice. Anything tramat does must beat the baseline of "just prompt the agent" — where it can't, stay out of the way.

## Rule 1 — read tramat.yml first

Before planning or writing any data code in a repo, read `tramat.yml` at the repo root. It has two sections:

- `conventions:` — naming, layout, compute. These are the repo's *choices*, not suggestions to re-derive. Never contradict a recorded convention without the user asking.
- `graph:` — the data graph: every step, what it reads and writes, how each edge is known, whether a retry is signed as safe. **This file is the source of truth about the pipeline topology — not your reading of the code, not the DAB task order.**

No `tramat.yml`? The repo hasn't onboarded. Say so; do not invent one ad hoc. `/tramat:doctor` checks the environment either way.

## Rule 2 — provenance or it didn't happen

Every read/write edge carries `via:` — exactly one of:

- `declared` — a human stated it.
- `observed` — Unity Catalog lineage saw it happen.
- `inferred` — static analysis guessed it from code. **Weakest tier.** An inferred edge means the wave order may be wrong; flag it in any plan that depends on it, and prefer confirming via UC lineage.

Never write an edge without `via:`. Never upgrade provenance yourself — only reconciliation against UC lineage turns `inferred`/`declared` into `observed`.

## Rule 3 — idempotency is signed, or it doesn't exist

`idempotency.safe: true` is meaningless without `confirmed_by` + `confirmed_at` — a safety claim nobody signed is treated as **unsafe** (and `graph.py` makes the unsigned claim an error). Never set `safe: true` yourself; propose it and ask the user to sign. Never retry a step in place unless it is retry-safe *per the manifest*: signed, no `side_effects`, strategy concrete. A wrongly-retried append duplicates client data with nothing downstream erroring — this is the disease tramat exists to prevent.

If you change a step's write mode, partition key, or merge key, the existing confirmation is **stale**: say so and get it re-signed.

## Rule 4 — deterministic questions get deterministic answers

Never re-derive by reading code what a plugin script computes. From the plugin root (`${CLAUDE_PLUGIN_ROOT}`):

| Question | Run |
|---|---|
| Is the manifest valid? What can run in parallel? What's next? | `python3 scripts/graph.py tramat.yml` |
| Does the code / UC lineage match the declared graph? | `python3 scripts/reconcile.py tramat.yml --src src/` |
| Does this helper already exist? Who uses it? | `python3 scripts/repomap.py --bundle databricks.yml --src src` |
| Is the environment healthy? | `python3 scripts/doctor.py` |

An undeclared write found by reconcile is an **error to fix** (declare it or remove it), never noise to suppress.

## Rule 5 — governance tiers

Files rendered by tramat carry a tier in `.tramat/applied.json`:

- **enforced** — doctor re-renders and diffs; hand edits surface as drift. Change via manifest + re-render, or adopt into an override. Kept deliberately tiny.
- **seeded** — generated once, then project-owned. Edit freely.
- **merged** — doctor checks required keys/blocks only; the rest is project-owned.

## Naming (standard mode)

Schema-per-source: catalog = environment (from `conventions.naming.catalog_per_env`), schema = source/domain, layer as table suffix (`players_bronze` / `players_silver`), `dim_*`/`fct_*` allowed in gold when `gold_semantic: true`. Landing files in UC Volumes. In `mode: adapted` repos the recorded conventions win, whatever they are.

## Databricks skills — defer, never reimplement

The Databricks *how* lives in the official databricks plugin skills (`databricks-core`, `databricks-dabs`, `databricks-pipelines`, `databricks-jobs`, `databricks-metric-views`, `databricks-unity-catalog`, `databricks-dbsql`, `databricks-execution-compute`, `databricks-data-discovery`, `databricks-lakeflow-connect`, `databricks-genie-agents`, `databricks-ml-training`). Tramat owns only the *what-goes-where*. Upstream has renamed skills before — current alias map: `databricks-bundles` → `databricks-dabs`, `databricks-spark-declarative-pipelines` → `databricks-pipelines`. Workspace-environment problems go to `/databricks:doctor`, not tramat.

## Token economy (applies to every tramat skill and command)

- Thin skill bodies; load `references/` files only when needed (progressive disclosure).
- Never dump full files or logs into context when a targeted read serves.
- Long-output work — repo surveys, deploy/poll loops — belongs in subagents.
- Output terse and information-dense; findings over narration.

## Layering

Commands never invoke commands. Shared behavior lives in skills; commands compose skills and scripts. (Currently shipped: `/tramat:doctor`, `/tramat:help` — the stage machine and scaffold commands land in later milestones; `/tramat:help` shows the roadmap.)
