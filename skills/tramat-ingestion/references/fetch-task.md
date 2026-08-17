# Reference: the fetch task

Worked example for `src/<package>/sources/<source>/fetch.py` — adapt names, auth, and entities to the interview; keep the bones. Assumes the repo's seeded helpers (`env`, `hashing`, `qa`).

Wire it as a `python_wheel_task` via a console script in `pyproject.toml`:

```toml
[project.scripts]
fetch-<source> = "<package>.sources.<source>.fetch:main"
```

```python
"""Fetch <source> entities to the landing Volume.

Job task, serverless. Talks to the external world; writes raw JSONL only.
Parsing/typing belongs to the SDP pipeline, not here.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import requests

from <package>.env import get_param
from <package>.hashing import filter_records_needing_update
from <package>.delta import get_spark

logger = logging.getLogger(__name__)

BASE_URL = "https://api.<source>.example"
ENTITY = "players"                       # one fetch module per entity, or parameterize


def fetch_entities(since: str | None, token: str) -> list[dict]:
    """Pull records from the API; retries/backoff live here, nowhere else."""
    params = {"since": since} if since else {}
    resp = requests.get(
        f"{BASE_URL}/v1/{ENTITY}",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["data"]


def latest_watermark(spark, bronze_table: str, column: str = "updated_at") -> str | None:
    """Incremental key from bronze — bronze is the fetcher's own memory."""
    if not spark.catalog.tableExists(bronze_table):
        return None
    row = spark.sql(f"SELECT MAX({column}) AS wm FROM {bronze_table}").collect()[0]
    return str(row["wm"]) if row["wm"] else None


def write_landing(records: list[dict], landing_dir: str, run_id: str) -> str:
    """One JSONL file per run under dt=/run= so Auto Loader picks it up incrementally."""
    dt = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = f"{landing_dir}/{ENTITY}/dt={dt}/run={run_id}.jsonl"
    payload = "\n".join(json.dumps(r, default=str) for r in records)
    # Volumes paths are writable as local files on serverless
    import os

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(payload)
    return path


def main(argv: list[str] | None = None) -> None:
    # python_wheel_task named_parameters arrive as CLI ARGS (--CATALOG=x), NOT
    # env vars — argparse with get_param defaults serves both jobs and local runs.
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--CATALOG", default=get_param("CATALOG"))
    ap.add_argument("--JOB_RUN_ID", default=get_param("JOB_RUN_ID", default=""))
    args = ap.parse_args(argv)
    if not args.CATALOG:
        raise RuntimeError("CATALOG is required (named parameter or env var)")

    spark = get_spark()
    token = get_param("<SOURCE>_TOKEN", required=True)   # secret via env/secret scope; never in code
    run_id = args.JOB_RUN_ID or datetime.now(timezone.utc).strftime("%H%M%S")
    bronze = f"{args.CATALOG}.<source>.{ENTITY}_bronze"

    records = fetch_entities(latest_watermark(spark, bronze), token)
    changed = filter_records_needing_update(spark, records, bronze, key_field="id")

    if not changed:
        logger.info("nothing new from <source>; signalling skip")
        try:
            from databricks.sdk import WorkspaceClient

            qa_dbutils = WorkspaceClient().dbutils
            from <package>.qa import signal_skip

            signal_skip(qa_dbutils, "no new <source> records")
        except Exception:
            pass
        return

    from <package>.env import LANDING_VOLUME_PATTERN

    landing = LANDING_VOLUME_PATTERN.format(catalog=args.CATALOG, source="<source>")
    path = write_landing(changed, landing, run_id)
    logger.info("wrote %d records to %s", len(changed), path)


if __name__ == "__main__":
    main()
```

Notes that survive adaptation:

- **The incremental key comes from bronze**, not from a side-file — the pipeline's output is the fetcher's memory, so a wiped dev schema automatically triggers a full refetch.
- **Hash short-circuit before writing**: `filter_records_needing_update` keeps landing (and therefore bronze) append-only-with-meaning; unchanged upstream data costs one lookup.
- **Secrets** arrive via environment / secret scope reference in the job spec (`{{secrets/scope/key}}`), never hardcoded, never in `tramat.yml`.
- **Tests**: fetch logic is testable with `requests` mocked and a fake spark — mirror the seeded `tests/` fakes; cover happy path, empty response, API error, incremental vs full.
