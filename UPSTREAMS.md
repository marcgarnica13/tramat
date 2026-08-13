# Upstream influences

Every project tramat depends on or borrows concepts from, with the release observed and the date last reviewed. When updating tramat, diff each upstream since its `last_reviewed` and refresh the row.

| Upstream | What tramat took | Observed | Last reviewed |
|---|---|---|---|
| [databricks-agent-skills](https://github.com/databricks/databricks-agent-skills) + `databricks aitools` CLI | **Hard dependency**: the 30 databricks-* skills, MCP server, `/databricks:doctor`. Referenced by name, never vendored. Names have drifted across channels — keep the alias map current. | plugin v0.2.10 | 2026-08-13 |
| [openwiki](https://github.com/langchain-ai/openwiki) | Managed prose-knowledge layer over shared code; `AGENTS.md`/`CLAUDE.md` pointers; CI refresh. Cost-guarded: shared-code scope only. | (npm, unpinned) | 2026-08-13 |
| [superpowers](https://github.com/obra/superpowers) | Brainstorming discipline; state-in-artifacts (plans/design docs), minimal config. | main | 2026-08-13 |
| [mattpocock/skills](https://github.com/mattpocock/skills) | **Watch closely.** Grilling interview primitive; user-invoked vs model-invoked layering rule (commands never invoke commands); two-axis code review; wizard pattern for human-only steps; diagnosing-bugs gated loop; CONTEXT.md shared language. | main | 2026-08-13 |
| [lisa](https://github.com/CodySwannGT/lisa) | Manifest + state dir + doctor + tiered templates (enforced/seeded/merged); session rules; sprint-loop → tramat's post-PR loop (CodeRabbit address-or-reject → resolve → merge gate → automerge). | main | 2026-08-13 |
| [caveman](https://github.com/juliusbrussee/caveman) | Token economy: progressive disclosure, no full-file dumps, long-output work in subagents, terse output. Concepts only — no dependency on the engine/proxy. | main | 2026-08-13 |
| [ponytail](https://github.com/dietrichgebert/ponytail) | The decision ladder as write-code protocol (exists? in repo? stdlib? dependency? one line? then minimal) — embedded in tramat-reuse and the reviewer. | main | 2026-08-13 |
