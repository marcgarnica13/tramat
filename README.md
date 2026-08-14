# tramat

**An AI agent harness for data engineering on Databricks.** Contract-first specs, a checked-in data graph, deterministic reconciliation — so your coding agent ships pipelines that are *provably* what you asked for, and your lakehouse never silently rots again.

Every data team knows the disease: the job that reports **SUCCESS** while writing zero rows. The scraper that quietly re-fetches nothing for six months. The "quick fix" that becomes seven PRs in three days because each fix exposed the next. The agent that writes a fourth copy of a helper that already exists. Tramat exists to make those failure modes *structurally impossible* — not by trusting the model harder, but by giving it artifacts it can't lie to.

## The three ideas

1. **The contract is the spec.** Every asset gets a data contract (ODCS). A contract's completeness is *computable* — every column either has its type, null semantics, grain, and at least one falsifiable assertion, or it doesn't. Loops get a stopping rule instead of a vibe.
2. **The graph is an artifact, not an inference.** `tramat.yml` carries your data graph: every step, what it reads and writes, *how you know* (`declared` by a human, `observed` from Unity Catalog lineage, or merely `inferred` from code — never confused), and whether a human signed off that a retry is safe. It's checked in. A change to your data graph is a diff someone approves.
3. **Reconciliation is enforcement.** Three views of reality — the declared graph, what the code actually does, what UC lineage actually saw — diffed deterministically. An undeclared write is an *error*, because an undeclared write is precisely what turns a retry into duplicated client data.

## What works today

**As a Claude Code plugin (M3):** this repo is a plugin marketplace. Installing it gets you `/tramat:init` (greenfield scaffold: manifest, DAB skeleton, seeded `src/` helpers with passing tests, CI — Tier-0 green out of the box), `/tramat:doctor` (environment + manifest checks + enforced-file drift, delegating workspace health to the official Databricks plugin), `/tramat:help`, the `tramat-core` operating rules for any repo with a `tramat.yml`, and two hooks — a sub-100ms session-start probe that tells the agent where the graph stands, and an advisory guard when enforced-tier rendered files are edited by hand. Every file tramat generates flows through one renderer (`scripts/render.py`) and is recorded in `.tramat/applied.json` with a governance tier — that single funnel is what kills sed-drift and vendored-copy drift.

```
/plugin marketplace add marcgarnica13/tramat
/plugin install tramat@tramat
```

**As three standalone scripts (M1):** Python ≥3.10 + PyYAML, nothing else, zero footprint in your repo.

### 🗺 `graph.py` — validate the graph, compute the waves

Declare your steps once:

```yaml
# tramat.yml (excerpt)
graph:
  defaults: {catalog: acme_prod, dev_catalog: acme_dev}
  budget: {tokens: 2000000, dbus: 40, on_breach: halt_and_report}
  steps:
    - id: conform_players
      status: shipped
      task: silver_player_conformed
      entrypoint: src/silver/conform_players.py
      reads:
        - {ref: bronze.impect_events, via: observed}      # UC lineage saw it
      writes:
        - {ref: silver.player_conformed, kind: primary, via: observed}
        - {ref: silver._quarantine_players, kind: quarantine, via: observed}
      idempotency:
        safe: true
        strategy: merge_on_key
        merge_key: [player_id, match_date]
        confirmed_by: marc          # a human signed this — unset means UNSAFE,
        confirmed_at: 2026-07-14    # and the loop will never retry it in place
      contract: contracts/silver/player_conformed.yaml
```

Then ask tramat what the world looks like:

```console
$ python3 scripts/graph.py examples/acme-lakehouse/tramat.yml
planned: 1  implemented: 1  tested: 1  shipped: 4   (7 steps)

wave 1
  shipped      ingest_impect_events
  shipped      scrape_transfermarkt  [no-retry]
wave 2
  shipped      conform_players
  shipped      legacy_shot_pipeline  [VIOLATES, manual]
  tested       normalise_valuations  [inferred-edge]
wave 3
  implemented  build_valuation_weekly
wave 4
  planned      train_talent_id  [no-retry]

next: normalise_valuations  tested -> shipped

[warn ] normalise_valuations: read bronze.tm_valuations is inferred from code — wave order may be wrong
```

Waves tell you what can safely run **in parallel**. The picker tells an autonomous loop the *one* correct next move. Brownfield steps that break the rules stay legible (`[VIOLATES, manual]`) — flagged and fenced off from automation, never hidden. And a malformed manifest produces findings, not YAML archaeology:

```console
[error] b: idempotency.safe without confirmed_by/confirmed_at — a safety claim nobody signed
[error] <graph>: serialize references unknown step 'ghost_step' — the constraint it encodes is not being enforced
```

### 🔍 `reconcile.py` — declared × code × lineage

```console
$ python3 scripts/reconcile.py tramat.yml --src src/ --lineage lineage.json
[error] build_valuation_weekly: undeclared write to gold._tmp_debug (per lineage) — an undeclared write is what breaks a retry
[error] scrape_transfermarkt: write mode ['append'] does not match strategy 'overwrite_partition' confirmed on 2026-07-14 — idempotency confirmation is stale, re-confirm before the loop may retry this step
[warn ] conform_players: 3 table refs built dynamically; static analysis is incomplete here — rely on UC lineage
```

That second finding is the crown jewel: someone changed a write mode *after* a human confirmed the retry semantics — reconcile catches the stale signature before an automated retry duplicates data. No manifest yet? Start with the brownfield inventory:

```console
$ python3 scripts/reconcile.py --inventory --src src/
src/silver/conform_players.py
  reads: bronze.impect_events
  WRITES: silver.player_conformed
  dynamic refs: 2
...
13 files touch tables statically — rely on UC lineage for the 24 dynamic refs
```

### 📇 `repomap.py` — who already wrote that helper

```console
$ python3 scripts/repomap.py --bundle databricks.yml --src src --out docs/repo
50 tasks (50 resolved), 85 modules, 16 unused
```

It walks your Databricks Asset Bundle → jobs → tasks → entrypoints → *transitive imports*, and builds the reverse index an agent cannot get by querying anything: **"who uses this function?"** That's the index that stops a coding agent writing the fourth copy of `write_partitioned()`. It also finds the skeletons: modules no task reaches, and tasks whose declared entrypoint no longer exists. Run against three real production repos on day one, it found 16, 43, and 192 orphan candidates respectively — and one bundle whose task pointed at a file deleted months ago.

## Where this is going (v0.1)

The scripts are the deterministic core. The full harness — a Claude Code plugin — wraps them in an agent workflow:

- **A grinding contract interview** that turns "can we get a table with player valuations by week?" into a complete, validated contract *before any code is written* — grounded in real profiles of your actual data, one question at a time.
- **A stage machine** — Intake → Understand → Plan → Build → Prove → Learn — where Intake can *reject* (it probes your actual grants before burning two days of agent work on a table nobody can read), Prove demands evidence instead of assertions, and Learn promotes every hard-won trap into permanent knowledge.
- **A second AI as a gate**: plan-done and implementation-done, every piece of work optionally cross-reviewed by an independent model (Codex CLI adapter first). Two brains, structurally disagreeing on your behalf.
- **A post-PR loop** that addresses or rejects every review comment, resolves every conversation, and automerges only on green CI + cleared review — then feeds what the review taught back into the harness.
- All of it riding on the official [Databricks agent skills](https://github.com/databricks/databricks-agent-skills) — tramat sequences them, never reimplements them.

## Design principles

- **The harness helps; it never insists.** It recommends state-of-the-art defaults (Lakeflow Spark Declarative Pipelines, contract-first, medallion conventions) and complies when you choose otherwise. Everything must beat the baseline of "just prompt the agent" — or it stays out of the way.
- **Nothing lives in the conversation.** State is `tramat.yml` + `contracts/` + run files on disk. A crashed session, a new laptop, or a colleague picking it up all resume identically.
- **Deterministic where it must be.** Waves, undeclared-write detection, and reuse indexing are code, not vibes — and that code ships with the plugin, never with your repo.
- **Provenance or it didn't happen.** Every edge in the graph says how it's known. An inferred edge is flagged in every plan, because a wrong edge means two things running in parallel that shouldn't.

## Try it

```bash
git clone https://github.com/marcgarnica13/tramat
cd tramat
pip install pyyaml   # the one dependency
python3 scripts/graph.py examples/acme-lakehouse/tramat.yml
python3 scripts/repomap.py --bundle /path/to/your/repo/databricks.yml --src /path/to/your/repo/src
```

Point `repomap` at any Databricks Asset Bundle repo you have — it's read-only and needs no workspace access. If it finds nothing interesting, your repo is cleaner than most.

## Credits

Tramat stands on deliberate borrowing — see [UPSTREAMS.md](UPSTREAMS.md) for every influence, what we took, and when we last reviewed it.

## License

Apache-2.0.
