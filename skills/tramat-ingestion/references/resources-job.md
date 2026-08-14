# Reference: the resources YAML

Worked example for `resources/<source>.yml` — one file per source, defining the SDP pipeline and the job that runs fetch → pipeline. Serverless throughout (the default; classic goes through `tramat-compute`).

```yaml
resources:
  pipelines:
    <source>_pipeline:
      name: "<source> - ${bundle.target}"
      serverless: true
      catalog: ${var.CATALOG}          # catalog = environment
      schema: <source>                 # schema-per-source
      libraries:
        - glob:
            include: ../pipelines/<source>/**
      configuration:
        catalog: ${var.CATALOG}        # read in pipeline code via spark.conf
      tags:
        data_source: "<source>"
        environment: "${var.DEPLOYMENT_ENV}"

  jobs:
    <source>_ingest:
      name: "<source> ingest - ${bundle.target}"
      tags:
        data_source: "<source>"
        environment: "${var.DEPLOYMENT_ENV}"

      environments:
        - environment_key: serverless-<source>
          spec:
            environment_version: "4"
            dependencies:
              - ../dist/*.whl

      tasks:
        - task_key: fetch
          description: "Fetch <source> to landing Volume (hash short-circuit inside)"
          # HANG-GUARD, not a runtime budget: external calls hang (observed 33h
          # stuck scrapes upstream). Size generously; consider a per-target
          # variable when dev fetches a subset and prod fetches everything.
          timeout_seconds: 3600
          environment_key: serverless-<source>
          python_wheel_task:
            package_name: <package>
            entry_point: fetch-<source>          # [project.scripts] in pyproject
            named_parameters:
              CATALOG: ${var.CATALOG}
              JOB_RUN_ID: "{{job.run_id}}"

        - task_key: refresh_pipeline
          depends_on:
            - task_key: fetch
          pipeline_task:
            pipeline_id: ${resources.pipelines.<source>_pipeline.id}

      max_concurrent_runs: 1           # overlapping fetches corrupt the watermark logic
      queue:
        enabled: true
```

Rules that survive adaptation:

- **No schedule here.** Schedules live only under `targets.prod.resources` in `databricks.yml` (doctor warns otherwise). Dev/staging run on demand.
- **`max_concurrent_runs: 1`** on ingest jobs — two concurrent fetches race the watermark and double-write landing.
- **Tags** (`data_source`, `environment`) on both job and pipeline — cost attribution needs them later.
- Wheel attach on serverless = `environments[].spec.dependencies`; classic uses `libraries:` per task instead (see `tramat-compute` — mixing them up is the most common deploy failure).
- After writing this file, declare the step in `tramat.yml` `graph:` — task = job name, writes = the bronze/silver tables `via: declared`, `side_effects: [external_http]` on fetch, idempotency proposed and left for the user to sign.
