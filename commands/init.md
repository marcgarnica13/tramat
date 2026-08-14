---
description: Set up a new tramat-managed Databricks repo in the current directory — you compose it from the proven starter example (manifest, DAB skeleton, src/ helpers with passing tests, CI), adapted to the user's answers. Greenfield only; existing bundle repos onboard instead.
---

Set up a canonical tramat repo in the current directory. Greenfield only.

There is no renderer and no fill-in-the-blanks step: **you** compose the repo, with the shipped example as a proven starting point — copy what fits verbatim, adapt what doesn't, and skip what the user doesn't want. The plan and the developer decide; the example keeps you honest about what a green repo looks like.

## 1. Refuse when this isn't greenfield

- `databricks.yml` exists → brownfield bundle repo. Say so and stop: `/tramat:onboard` (future milestone) records existing conventions without touching files; init must not overwrite a living bundle.
- `tramat.yml` exists → already initialized; suggest `/tramat:doctor` instead.

Other files (`.git`, README, editor config) are fine — leave them alone.

## 2. Interview

Take values from `$ARGUMENTS` where given; otherwise ask (AskUserQuestion, one round). Never invent workspace hosts, catalogs, or service principals:

- **project name** — default: current directory name; python package name derived snake_case, confirmed.
- **workspace host(s)** — the `https://…` URL(s). If the user is unsure, `~/.databrickscfg` profiles list candidate hosts — let them pick; never auto-select.
- **catalogs per env** — catalog = environment (e.g. `acme_dev`, `acme_staging`, `acme`). Fewer or more environments than dev/staging/prod is the user's call.
- **run_as service principal** — strongly recommended: a personal-identity `run_as` breaks every deploy after that person leaves. If the user has none, say so, point at the `databricks-unity-catalog` skill to create one, and respect their choice if they proceed without (doctor will keep flagging it as an advisory).

## 3. Compose the repo

The starting point is `${CLAUDE_PLUGIN_ROOT}/examples/starter-lakehouse/` — a complete repo kept Tier-0 green in tramat's CI. Read it, then write this repo's version of each piece, adapted to the interview:

- `tramat.yml` — conventions + empty `graph:`; must validate against `${CLAUDE_PLUGIN_ROOT}/schemas/tramat.schema.json`.
- `databricks.yml` — bundle name, targets/catalog variables, `run_as`, pinned hosts (the example leaves the host to the profile; a real repo pins it).
- `src/<package>/` helpers + `tests/` — the example's five modules (env, delta, merge, hashing, qa) encode hard-won lessons (CDF-on-create, VOID-column defense, hash short-circuits, row-count-drop gate); take them unless the user objects, fixing the package name and catalog map.
- `pyproject.toml`, `.pre-commit-config.yaml`, `.gitignore`, `CLAUDE.md`, `AGENTS.md`, `README.md`, `docs/runbook.md`, `.github/workflows/pr-checks.yml`.

Deviations from the example are fine — they're the point. Just keep `tramat.yml` truthful about whatever conventions this repo actually adopts.

Watch for example-only artifacts when copying: the example's `.gitignore` ignores `uv.lock` (so tramat's CI resolves fresh) — a real repo should commit its lockfile, so drop that ignore. The example also pins no `workspace.host`; a real repo pins it.

If the directory is not a git repo, `git init` and stage everything; commit only if the user asks.

## 4. Verify — Tier 0, all of it

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --repo-only .
```

Then `databricks bundle validate` — this needs workspace auth: ask which profile to use (`--profile <name>`, never pick one for them); skip with a note if they defer.

A fresh init must end green. If any gate fails, fix it before reporting done — a scaffold that starts red normalizes red.

## 5. Report

Terse summary: what was set up, where it deviates from the starter example and why, Tier-0 status, and next steps — add the first source once `/tramat:new-source` ships; until then `resources/` + `pipelines/` are hand-authored with the official `databricks-pipelines` / `databricks-jobs` skills, and every new step gets declared in `tramat.yml` `graph:` with `via:` provenance.
