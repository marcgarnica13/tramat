"""Generic Delta upsert via MERGE INTO.

SQL construction is separated from execution so the statement itself is unit
tested. Identifiers are backtick-quoted; values never travel through SQL
strings (the source DataFrame is exposed as a temp view).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from .delta import delta_writer, get_spark

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession


def quote_identifier(identifier: str) -> str:
    """Backtick-quote a possibly dotted identifier (``cat.sch.tbl``)."""
    parts = identifier.split(".")
    for part in parts:
        if not part or "`" in part:
            raise ValueError(f"invalid identifier: {identifier!r}")
    return ".".join(f"`{part}`" for part in parts)


def build_merge_sql(target_table: str, source_view: str, columns: Sequence[str], keys: Sequence[str]) -> str:
    """MERGE statement upserting ``columns`` from ``source_view`` into ``target_table`` on ``keys``."""
    missing = [k for k in keys if k not in columns]
    if missing:
        raise ValueError(f"merge keys not in columns: {missing}")
    if not keys:
        raise ValueError("at least one merge key is required")

    on = " AND ".join(f"target.{quote_identifier(k)} = source.{quote_identifier(k)}" for k in keys)
    update_cols = [c for c in columns if c not in keys]
    update = ", ".join(f"{quote_identifier(c)} = source.{quote_identifier(c)}" for c in update_cols)
    insert_cols = ", ".join(quote_identifier(c) for c in columns)
    insert_vals = ", ".join(f"source.{quote_identifier(c)}" for c in columns)

    matched = f"WHEN MATCHED THEN UPDATE SET {update}\n" if update_cols else ""
    return (
        f"MERGE INTO {quote_identifier(target_table)} AS target\n"
        f"USING {quote_identifier(source_view)} AS source\n"
        f"ON {on}\n"
        f"{matched}"
        f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"
    )


def upsert(
    df: DataFrame,
    table_name: str,
    keys: Sequence[str],
    *,
    spark: SparkSession | None = None,
) -> dict[str, int]:
    """Upsert ``df`` into ``table_name`` on ``keys``; creates the table if missing.

    Returns ``{"inserted", "updated", "total_processed"}``.
    """
    if spark is None:
        spark = get_spark()

    if not spark.catalog.tableExists(table_name):
        delta_writer(df, mode="overwrite").saveAsTable(table_name)
        total = df.count()
        return {"inserted": total, "updated": 0, "total_processed": total}

    initial = spark.table(table_name).count()
    view = "_tramat_upsert_source"
    df.createOrReplaceTempView(view)
    spark.sql(build_merge_sql(table_name, view, df.columns, keys))
    final = spark.table(table_name).count()
    source = df.count()
    inserted = max(final - initial, 0)
    return {"inserted": inserted, "updated": max(source - inserted, 0), "total_processed": source}
