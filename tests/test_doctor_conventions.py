"""Doctor's semantic bundle-convention checks — the replacement for byte-diffing."""

from __future__ import annotations

import doctor


def write_repo(tmp_path, bundle_yaml: str, with_workflow: bool = False):
    (tmp_path / "databricks.yml").write_text(bundle_yaml, encoding="utf-8")
    if with_workflow:
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "checks.yml").write_text("name: checks\non: pull_request\n", encoding="utf-8")
    return tmp_path


def run_checks(repo):
    doc = doctor.Doctor(repo=repo)
    doc.check_bundle_conventions(yaml_ok=True)
    return {c.name: c for c in doc.checks}


def test_skips_without_bundle(tmp_path):
    checks = run_checks(tmp_path)
    assert checks["bundle-conventions"].status == "skip"


def test_sp_run_as_is_ok(tmp_path):
    repo = write_repo(tmp_path, "run_as:\n  service_principal_name: sp-x\n", with_workflow=True)
    checks = run_checks(repo)
    assert checks["run-as"].status == "ok"
    assert checks["ci-present"].status == "ok"


def test_personal_or_missing_run_as_warns(tmp_path):
    repo = write_repo(tmp_path, "run_as:\n  user_name: someone@example.com\n")
    assert run_checks(repo)["run-as"].status == "warn"
    (repo / "databricks.yml").write_text("bundle:\n  name: x\n", encoding="utf-8")
    assert run_checks(repo)["run-as"].status == "warn"


def test_unpaused_schedule_outside_prod_warns(tmp_path):
    repo = write_repo(
        tmp_path,
        """
run_as:
  service_principal_name: sp-x
targets:
  dev:
    resources:
      jobs:
        nightly:
          schedule:
            quartz_cron_expression: "0 0 6 * * ?"
  prod:
    mode: production
    resources:
      jobs:
        nightly:
          schedule:
            quartz_cron_expression: "0 0 6 * * ?"
""",
    )
    check = run_checks(repo)["schedules-prod-only"]
    assert check.status == "warn"
    assert "dev:nightly" in check.detail
    assert "prod:nightly" not in check.detail


def test_paused_schedule_outside_prod_is_fine(tmp_path):
    repo = write_repo(
        tmp_path,
        """
run_as:
  service_principal_name: sp-x
targets:
  staging:
    resources:
      jobs:
        nightly:
          schedule:
            quartz_cron_expression: "0 0 6 * * ?"
            pause_status: PAUSED
""",
    )
    assert run_checks(repo)["schedules-prod-only"].status == "ok"


def test_bundle_wide_schedule_warns(tmp_path):
    repo = write_repo(
        tmp_path,
        """
run_as:
  service_principal_name: sp-x
resources:
  jobs:
    sweeper:
      trigger:
        periodic:
          interval: 1
          unit: HOURS
""",
    )
    check = run_checks(repo)["schedules-prod-only"]
    assert check.status == "warn"
    assert "(all targets):sweeper" in check.detail


def test_missing_ci_is_info_not_error(tmp_path):
    repo = write_repo(tmp_path, "run_as:\n  service_principal_name: sp-x\n")
    assert run_checks(repo)["ci-present"].status == "info"
