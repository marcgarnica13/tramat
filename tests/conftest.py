"""Test setup for tramat's own scripts (stdlib + PyYAML + pytest only)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

#: one full variable set for the repo template group, used across tests
REPO_VARS = {
    "project_name": "aurora-lakehouse",
    "package": "aurora_lakehouse",
    "workspace_host": "https://example.cloud.databricks.com",
    "dev_catalog": "aurora_dev",
    "staging_catalog": "aurora_staging",
    "prod_catalog": "aurora",
    "run_as_sp": "sp-aurora-bundles",
}


@pytest.fixture()
def rendered_repo(tmp_path):
    """A fresh repo-group render in a temp dir."""
    import render

    render.cmd_apply("repo", tmp_path, dict(REPO_VARS), force=False)
    return tmp_path
