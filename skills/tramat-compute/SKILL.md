---
name: tramat-compute
description: Compute assignment for every job task and SDP pipeline in a tramat repo — serverless by default, classic job clusters only via a named profile with a recorded reason, and the mechanical differences (wheel attach, security mode, log delivery) that break deploys when mixed up. Read before writing or editing any compute block in resources YAML.
---

# tramat-compute

**Serverless is the default for everything** — every job task and every SDP pipeline — unless `tramat.yml` `conventions.compute.assignments` maps it to a named classic profile. No unrecorded classic compute, ever: the reason lives in the profile, not in tribal memory.

## When classic is justified

| Reason | Example |
|---|---|
| Library unavailable on serverless | Snowflake Spark connector writes |
| Custom `spark_conf` / instance control the workload genuinely needs | memory-heavy driver for a big collect; delta autoCompact tuning |
| GPU / ML training profile | training jobs (tramat-ml, later) |
| Long-running scraper wanting spot economics | multi-hour fetches on `SPOT_WITH_FALLBACK` |

Anything else: stay serverless. If a classic assignment's reason disappears (library lands on serverless), retire the profile.

## Recording

Every classic use = a named profile in `tramat.yml` with a `reason`, plus an assignment:

```yaml
conventions:
  compute:
    default: serverless
    serverless: { environment_version: "4" }
    classic_profiles:
      snowflake-writer:
        reason: "Snowflake Spark connector unavailable on serverless"
        spark_version: 16.4.x-scala2.12
        data_security_mode: SINGLE_USER
        node_type: { dev: m5.large, prod: m5d.xlarge }
        workers: { dev: 1, prod: 4 }
        spot: SPOT_WITH_FALLBACK
    assignments:
      transfermarkt_snowflake_dump: snowflake-writer
```

## The mechanics that break deploys

- **Wheel attach differs**: serverless = `environments[].spec.dependencies: [../dist/*.whl]` on the job + `environment_key` per task; classic = `libraries: [{whl: ../dist/*.whl}, {requirements: ../requirements.txt}]` **per task** + `job_cluster_key`. Mixing the two is the most common deploy failure.
- **Classic clusters that install the bundle wheel need `data_security_mode: SINGLE_USER`** — shared access mode (USER_ISOLATION) cannot load cluster libraries from the bundle's `/Workspace` internal wheel (WSFS credential forwarding fails → FileNotFoundException).
- **`cluster_log_conf` volume destinations must have NO trailing slash** — `bundle validate` passes, `terraform apply` rejects it at deploy time. Validate ≠ deploy validation.
- **Env vars**: classic clusters forward `spark_env_vars` (`DEPLOYMENT_ENV`, `CATALOG`); serverless tasks get parameters via `named_parameters`/`base_parameters` instead — the repo's `env.py` resolution chain absorbs the difference.
- Serverless environment version comes from `conventions.compute.serverless.environment_version`; bump it deliberately, repo-wide, not per-job.

Exact field syntax: defer to `databricks-jobs` / `databricks-pipelines`. Worked YAML for both modes: `references/serverless-vs-classic.md`.
