---
description: Scaffold a new tramat-managed Databricks repo in the current directory — manifest, DAB skeleton, seeded src/ helpers with passing tests, CI. Greenfield only; existing bundle repos onboard instead.
---

Scaffold a canonical tramat repo in the current directory. Greenfield only.

## 1. Refuse when this isn't greenfield

- `databricks.yml` exists → this is a brownfield bundle repo. Say so and stop: `/tramat:onboard` (future milestone) records existing conventions without touching files; init must not overwrite a living bundle.
- `tramat.yml` exists → already initialized; suggest `/tramat:doctor` instead.

Other files (`.git`, README, editor config) are fine — seeded/merged templates skip existing files; only an enforced-tier collision aborts.

## 2. Gather the variables

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render.py" vars repo` for the authoritative list. Take values from `$ARGUMENTS` where given; otherwise ask (AskUserQuestion, one round). Never invent workspace hosts, catalogs, or service principals:

- `project_name` — default: current directory name.
- `package` — python package name; derive `project_name` → snake_case and confirm.
- `workspace_host` — the `https://…` workspace URL. If the user is unsure, `~/.databrickscfg` profiles list candidate hosts — let them pick; never auto-select.
- `dev_catalog` / `staging_catalog` / `prod_catalog` — catalog = environment (e.g. `acme_dev`, `acme_staging`, `acme`).
- `run_as_sp` — service principal (application id or name) jobs run as. Mandatory: a personal-identity `run_as` breaks every deploy after that person leaves. If the user has none yet, point at the `databricks-unity-catalog` skill to create one; do not scaffold without it.

## 3. Render

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render.py" apply repo --dest . \
  --var project_name=... --var package=... --var workspace_host=... \
  --var dev_catalog=... --var staging_catalog=... --var prod_catalog=... \
  --var run_as_sp=...
```

Every rendered file lands in `.tramat/applied.json` with its governance tier. If the directory is not a git repo, `git init` and stage everything (including `.tramat/`); commit only if the user asks.

## 4. Verify — Tier 0, all of it

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render.py" check --dest .
```

Then `databricks bundle validate` — this needs workspace auth: ask which profile to use (`--profile <name>`, never pick one for them); skip with a note if they defer.

A fresh init must end green. If any gate fails, fix it before reporting done — a scaffold that starts red normalizes red.

## 5. Report

Terse summary: what was rendered (count by tier), Tier-0 status, and next steps — add the first source once `/tramat:new-source` ships; until then `resources/` + `pipelines/` are hand-authored with the official `databricks-pipelines` / `databricks-jobs` skills, and every new step gets declared in `tramat.yml` `graph:` with `via:` provenance.
