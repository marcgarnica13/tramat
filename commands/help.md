---
description: What tramat is, what's installed and working now, and where each command lives on the roadmap.
---

Orient the user in tramat. Answer whatever they asked (`$ARGUMENTS`); with no specific question, give the short tour below. Be terse — this is a router, not a manual.

## Available now

- `/tramat:init` — greenfield setup: the agent composes the repo (manifest, DAB skeleton, `src/` helpers with tests, CI) from the proven `examples/starter-lakehouse/` starting point, adapted to your answers — no fill-in-the-blanks templates. Refuses on existing bundle repos (those onboard instead).
- `/tramat:doctor` — environment + manifest checks (Databricks CLI/plugin/auth, tramat.yml schema, graph validation) plus semantic convention advisories (run_as pinned to an SP, schedules only in prod, Tier-0 CI present).
- Deterministic scripts (run directly from `${CLAUDE_PLUGIN_ROOT}/scripts/`):
  - `graph.py tramat.yml` — validate the data graph, compute parallel waves, pick the next step.
  - `reconcile.py tramat.yml --src src/ [--lineage lineage.json]` — diff declared graph × code × UC lineage; undeclared writes are errors. `--inventory` for brownfield discovery.
  - `repomap.py --bundle databricks.yml --src src` — bundle→task→import reverse index: who already wrote that helper; orphan modules; dead entrypoints.
- The `tramat-core` skill auto-applies in repos with a `tramat.yml`: manifest-first, edge provenance, signed idempotency, examples-as-starting-points.

## On the roadmap (not yet installed — don't attempt to invoke)

- Brownfield `/tramat:onboard`
- Stage machine: intake → understand → plan → build → prove → ship → learn, with a grinding contract interview (ODCS) and reject-capable intake
- Scaffolds: new-source, new-transform, new-dimension, new-star, new-metric-view, new-genie, new-model
- `/tramat:verify`, reuse gate + openwiki, `/tramat:pr-loop`, cross-AI second-opinion gate (codex), brain adapters

If the user asks for one of these, say it isn't built yet and offer the nearest working equivalent (usually a script above, or the official `databricks` plugin skills for Databricks mechanics).
