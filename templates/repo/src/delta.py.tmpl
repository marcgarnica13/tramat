"""Delta write helpers: CDF on every new table + NullType defense.

All Delta writes in this repo go through :func:`delta_writer` so every table
is born with Change Data Feed enabled. The option only takes effect at table
*create* time; enabling CDF on a pre-existing table is a one-off
``ALTER TABLE ... SET TBLPROPERTIES`` per environment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

CDF_TABLE_PROPERTIES = {"delta.enableChangeDataFeed": "true"}


def get_spark() -> SparkSession:
    """Active session: Databricks Connect when available, plain Spark otherwise."""
    try:
        from databricks.connect import DatabricksSession

        return DatabricksSession.builder.getOrCreate()
    except ImportError:
        from pyspark.sql import SparkSession

        return SparkSession.builder.getOrCreate()


def delta_writer(df: DataFrame, *, mode: str, merge_schema: bool = False, overwrite_schema: bool = False) -> Any:
    """Delta ``DataFrameWriter`` with CDF enabled at create time.

    Args:
        df: DataFrame to write.
        mode: save mode (``"overwrite"``, ``"append"``, ...).
        merge_schema: allow additive schema changes.
        overwrite_schema: allow full schema replacement.
    """
    writer = df.write.format("delta").option("delta.enableChangeDataFeed", "true")
    if merge_schema:
        writer = writer.option("mergeSchema", "true")
    if overwrite_schema:
        writer = writer.option("overwriteSchema", "true")
    return writer.mode(mode)


def null_type_columns(schema: Any) -> list[str]:
    """Names of top-level columns typed ``NullType`` (VOID)."""
    from pyspark.sql.types import NullType

    return [field.name for field in schema.fields if isinstance(field.dataType, NullType)]


def defend_null_types(df: DataFrame, cast_to: str | None = "string") -> DataFrame:
    """Neutralize VOID columns before a write poisons the table schema.

    A column that is all-``None`` infers as ``NullType``; once written, that
    column can never hold a value and some readers choke on it. Casts each
    such column to ``cast_to`` (default ``string``), or drops them when
    ``cast_to`` is ``None``.
    """
    columns = null_type_columns(df.schema)
    if not columns:
        return df
    if cast_to is None:
        return df.drop(*columns)
    for name in columns:
        df = df.withColumn(name, df[name].cast(cast_to))
    return df
