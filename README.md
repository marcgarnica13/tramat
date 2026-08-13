# tramat

An open-source Claude Code harness for data engineering on Databricks: contract-first specs, a checked-in data graph, deterministic reconciliation, and a stage machine that knows when it's done.

**Status: M1 (pre-release).** The plugin-internal scripts exist and run standalone; the plugin surface (skills, commands, agents) lands in M2+. Design spec: see `docs/`.

## What exists today

| Script | Does | Try it |
|---|---|---|
| `scripts/graph.py` | Load + validate the `graph:` section of `tramat.yml`: waves, provenance, signed idempotency, single-primary rule, next-step picker | `python3 scripts/graph.py examples/acme-lakehouse/tramat.yml` |
| `scripts/reconcile.py` | Three-way diff: declared graph × code (AST) × UC lineage. `--inventory` mode needs no manifest | `python3 scripts/reconcile.py --inventory --src <src>` |
| `scripts/repomap.py` | DAB bundle → tasks → transitive imports → reverse index ("who uses this helper"), orphan + stale-reference detection | `python3 scripts/repomap.py --bundle <databricks.yml> --src <src> --out docs/repo` |

Requirements: Python ≥3.10, `pyyaml`. No other dependencies; nothing gets installed into your repo.

## Design principles

- **The harness helps; it never insists.** It recommends state-of-the-art defaults (Lakeflow SDP, contract-first, medallion conventions) and complies when you choose otherwise.
- **The contract is the spec.** ODCS data contracts with computable completeness — loops get stopping rules, not judgement calls.
- **Nothing lives in the conversation.** State is `tramat.yml` + `contracts/` + run files on disk; any session resumes by reading them.
- **Deterministic where it must be.** Waves, undeclared-write detection, and reuse indexing are code, not vibes — and that code ships with the plugin, never with your repo.

## Credits & upstream influences

See [UPSTREAMS.md](UPSTREAMS.md) — tramat deliberately borrows from databricks-agent-skills, openwiki, superpowers, mattpocock/skills, GSD, lisa, caveman, and ponytail, and tracks each with a review timestamp.

## License

Apache-2.0.
