# Reference: serverless vs classic, side by side

Both blocks live inside a job under `resources/<source>.yml`. Distilled from a production repo that runs both on the same job (Delta tasks serverless, Snowflake-writing tasks classic).

## Serverless (the default)

```yaml
resources:
  jobs:
    my_job:
      environments:
        - environment_key: serverless-main
          spec:
            environment_version: "4"          # from conventions.compute.serverless
            dependencies:
              - ../dist/*.whl                 # wheel attaches HERE, job-level

      tasks:
        - task_key: process
          environment_key: serverless-main    # ← that's all a task needs
          python_wheel_task:
            package_name: my_package
            entry_point: my-entrypoint
            named_parameters:                 # params, not spark_env_vars
              CATALOG: ${var.CATALOG}
```

## Classic (only via a named profile in tramat.yml, with a reason)

```yaml
resources:
  jobs:
    my_job:
      job_clusters:
        - job_cluster_key: snowflake_writer_${bundle.target}
          new_cluster:
            spark_version: 16.4.x-scala2.12   # from the classic profile
            node_type_id: ${var.NODE_TYPE_ID}
            driver_node_type_id: ${var.DRIVER_NODE_TYPE_ID}
            num_workers: ${var.NUM_WORKERS}
            # SINGLE_USER (dedicated) is REQUIRED when tasks install the bundle
            # wheel: shared access mode can't load cluster libraries from the
            # bundle's /Workspace internal wheel (WSFS credential forwarding
            # fails → FileNotFoundException).
            data_security_mode: SINGLE_USER
            aws_attributes:
              zone_id: "auto"
              first_on_demand: 1
              availability: SPOT_WITH_FALLBACK
              ebs_volume_count: 1
              ebs_volume_type: GENERAL_PURPOSE_SSD
              ebs_volume_size: 100
            spark_env_vars:                   # classic forwards env vars
              DEPLOYMENT_ENV: ${bundle.target}
              CATALOG: ${var.CATALOG}
            # NO trailing slash: validate passes it, terraform apply rejects it.
            cluster_log_conf:
              volumes:
                destination: "/Volumes/${var.CATALOG}/<source>/landing/cluster_logs/my_job"

      tasks:
        - task_key: dump_to_snowflake
          job_cluster_key: snowflake_writer_${bundle.target}
          libraries:                          # wheel attaches HERE, task-level
            - whl: ../dist/*.whl
            - requirements: ../requirements.txt
          notebook_task:
            notebook_path: ../notebooks/dump.py
            base_parameters:
              CATALOG: ${var.CATALOG}
```

## The four asymmetries to memorize

| | Serverless | Classic |
|---|---|---|
| Wheel | `environments[].spec.dependencies`, job-level | `libraries: [{whl}, {requirements}]`, per task |
| Task binding | `environment_key` | `job_cluster_key` |
| Params | `named_parameters` / `base_parameters` | those + `spark_env_vars` on the cluster |
| Security mode | n/a | `SINGLE_USER` when installing the bundle wheel |
