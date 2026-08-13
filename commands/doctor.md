---
description: Check the tramat environment and this repo's manifest — Databricks CLI + official plugin at a tested version, auth profiles, PyYAML, tramat.yml schema + graph validation, codex availability.
---

Run tramat's deterministic doctor and interpret the results for the user.

1. Run:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --json
   ```

   (Add `--profile <name>` only if the user named a Databricks profile to verify — never pick one for them. `$ARGUMENTS`, if any, are passed through: a path checks that repo instead of cwd.)

2. Report findings grouped as **errors → warnings → info**, each with its hint. Keep it terse; do not restate healthy checks beyond a one-line summary.

3. Route follow-ups, don't fix blind:
   - Workspace/auth/environment failures → recommend `/databricks:doctor` (tramat delegates Databricks-environment health to the official plugin; never duplicate its checks).
   - Missing official plugin → `databricks aitools install`.
   - Manifest schema or graph errors → show the failing finding and offer to fix `tramat.yml`; re-run doctor after. For graph detail run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/graph.py" tramat.yml`.
   - No `tramat.yml` in a Databricks repo → mention `/tramat:onboard` (future milestone) records conventions without touching existing files; today, doctor simply reports the gap.
   - `codex` detected but second-opinion disabled → mention `review.second_opinion` can be enabled in `tramat.yml`; do not enable it unasked.

Doctor is read-only and makes no network calls except the Databricks CLI probes; it is safe to run anywhere.
