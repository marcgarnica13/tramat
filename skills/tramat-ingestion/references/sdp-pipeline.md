# Reference: the SDP pipeline

Worked example for `pipelines/<source>/bronze_silver.py`. The exact decorator API evolves — **confirm current syntax via the `databricks-pipelines` skill**; the shape below is the stable part.

```python
"""<source>: landing → bronze → silver (Lakeflow Spark Declarative Pipelines)."""

import dlt
from pyspark.sql import functions as F
from pyspark.sql.window import Window

CATALOG = spark.conf.get("catalog")          # set in the pipeline configuration
LANDING = f"/Volumes/{CATALOG}/<source>/landing/players"


@dlt.table(
    name="players_bronze",
    comment="Raw <source> players as fetched. Permissive: schema drift is rescued, not dropped.",
)
# Rescued-data check lives on BRONZE: expectations resolve against the output
# dataset, and silver drops _rescued — an expectation there fails analysis
# (proven the hard way in a live pipeline).
@dlt.expect("no_rescued_data", "_rescued IS NULL")
def players_bronze():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", f"/Volumes/{CATALOG}/<source>/landing/_schemas/players")
        .option("cloudFiles.inferColumnTypes", "true")
        .option("cloudFiles.rescuedDataColumn", "_rescued")
        .load(LANDING)
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
    )


@dlt.table(
    name="players_silver",
    comment="Typed, deduplicated <source> players. One row per natural key, latest wins.",
)
@dlt.expect_or_drop("valid_id", "id IS NOT NULL")
def players_silver():
    return (
        dlt.read("players_bronze")
        .withColumn("updated_at", F.to_timestamp("updated_at"))
        .withColumn(
            "_rn",
            F.row_number().over(
                # latest record per key; deterministic tie-break on ingest time
                Window.partitionBy("id").orderBy(F.col("updated_at").desc(), F.col("_ingested_at").desc())
            ),
        )
        .filter("_rn = 1")
        .drop("_rn", "_rescued")
    )
```

Failure economics: a deterministic analysis error (unresolvable column, bad expectation) still triggers the pipeline's internal `RETRY_ON_FAILURE` loop — observed ~25 min of serverless burned on identical failures. When a pipeline fails at *analysis* time, cancel the run; retrying cannot help. `bundle validate` cannot catch these — they surface only at pipeline analysis.

Shape rules:

- **Bronze**: Auto Loader (`cloudFiles`) over the landing directory; rescue column on; ingest metadata columns (`_ingested_at`, `_source_file`) for provenance. No business logic, no drops.
- **Silver**: typing, dedup on the natural key (latest wins), expectations. `expect_or_drop` only for rows that are unusable; plain `expect` for drift you want visible.
- **SCD dimensions** (`create_auto_cdc_flow`, `stored_as_scd_type=2`) are the modeling milestone's business — don't build them into the source pipeline.
- The pipeline's **catalog and target schema** come from the pipeline resource config (see `resources-job.md`): catalog = environment, target schema = `<source>`. No hardcoded catalog names in pipeline code — read from `spark.conf`.
