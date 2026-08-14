"""Hash-based change detection for incremental loads.

Fetchers short-circuit unchanged records by comparing a content hash against
what is already stored, so unchanged upstream data costs one lookup instead
of a rewrite.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)

#: column that stores each record's content hash
HASH_COLUMN = "content_hash"


def content_hash(data: Any) -> str:
    """Deterministic SHA-256 of any JSON-serializable structure (keys sorted)."""
    if isinstance(data, (dict, list)):
        payload = json.dumps(data, sort_keys=True, default=str)
    else:
        payload = str(data)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def identify_changes(
    records: Sequence[dict[str, Any]],
    key_field: str,
    existing_hashes: Mapping[str, str],
    *,
    hash_column: str = HASH_COLUMN,
) -> dict[str, list[dict[str, Any]]]:
    """Split records into ``new`` / ``changed`` / ``unchanged`` vs stored hashes.

    The hash is computed *before* stamping ``hash_column`` onto the record, so
    a record hashes identically on every run.
    """
    result: dict[str, list[dict[str, Any]]] = {"new": [], "changed": [], "unchanged": []}
    for record in records:
        key = str(record[key_field])
        digest = content_hash({k: v for k, v in record.items() if k != hash_column})
        record[hash_column] = digest
        if key not in existing_hashes:
            result["new"].append(record)
        elif existing_hashes[key] != digest:
            result["changed"].append(record)
        else:
            result["unchanged"].append(record)
    logger.info(
        "change detection: %d new, %d changed, %d unchanged",
        len(result["new"]),
        len(result["changed"]),
        len(result["unchanged"]),
    )
    return result


def get_existing_hashes(
    spark: SparkSession,
    table_name: str,
    key_column: str,
    key_values: Sequence[str],
    *,
    hash_column: str = HASH_COLUMN,
) -> dict[str, str]:
    """Fetch stored hashes for ``key_values``; empty dict if the table is missing."""
    if not key_values:
        return {}
    if not spark.catalog.tableExists(table_name):
        return {}
    escaped = ", ".join("'" + str(v).replace("'", "''") + "'" for v in key_values)
    rows = spark.sql(
        f"SELECT `{key_column}`, `{hash_column}` FROM {table_name} WHERE `{key_column}` IN ({escaped})"
    ).collect()
    return {str(row[key_column]): row[hash_column] for row in rows}


def filter_records_needing_update(
    spark: SparkSession,
    records: Sequence[dict[str, Any]],
    table_name: str,
    key_field: str,
    *,
    hash_column: str = HASH_COLUMN,
) -> list[dict[str, Any]]:
    """Records that are new or changed vs what ``table_name`` already stores."""
    if not records:
        return []
    keys = [str(record[key_field]) for record in records]
    existing = get_existing_hashes(spark, table_name, key_field, keys, hash_column=hash_column)
    changes = identify_changes(records, key_field, existing, hash_column=hash_column)
    return changes["new"] + changes["changed"]
