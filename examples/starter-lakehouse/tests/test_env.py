from __future__ import annotations

import pytest

from starter_lakehouse import env


@pytest.fixture(autouse=True)
def clean_environ(monkeypatch):
    for name in ("DEPLOYMENT_ENV", "CATALOG", "MY_PARAM"):
        monkeypatch.delenv(name, raising=False)


def test_get_param_default():
    assert env.get_param("MY_PARAM", "fallback") == "fallback"


def test_get_param_env_beats_default(monkeypatch):
    monkeypatch.setenv("MY_PARAM", "from-env")
    assert env.get_param("MY_PARAM", "fallback") == "from-env"


def test_get_param_widget_beats_env(monkeypatch, dbutils):
    monkeypatch.setenv("MY_PARAM", "from-env")
    dbutils.widgets.values["MY_PARAM"] = "from-widget"
    assert env.get_param("MY_PARAM", dbutils=dbutils) == "from-widget"


def test_get_param_blank_widget_falls_through(monkeypatch, dbutils):
    monkeypatch.setenv("MY_PARAM", "from-env")
    dbutils.widgets.values["MY_PARAM"] = "   "
    assert env.get_param("MY_PARAM", dbutils=dbutils) == "from-env"


def test_get_param_required_raises():
    with pytest.raises(RuntimeError, match="MY_PARAM"):
        env.get_param("MY_PARAM", required=True)


def test_deployment_env_default_and_validation(monkeypatch):
    assert env.get_deployment_env() == env.DEFAULT_ENV
    monkeypatch.setenv("DEPLOYMENT_ENV", "nope")
    with pytest.raises(RuntimeError, match="nope"):
        env.get_deployment_env()


@pytest.mark.parametrize("name", ["dev", "staging", "prod"])
def test_get_catalog_per_env(name):
    assert env.get_catalog(env=name) == env.CATALOGS[name]


def test_get_catalog_override_wins(monkeypatch):
    monkeypatch.setenv("CATALOG", "sandbox_catalog")
    assert env.get_catalog() == "sandbox_catalog"


def test_get_landing_dir(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ENV", "prod")
    expected = env.LANDING_VOLUME_PATTERN.format(catalog=env.CATALOGS["prod"], source="players")
    assert env.get_landing_dir("players") == expected


def test_setup_widgets_declares_and_exports(monkeypatch, dbutils):
    monkeypatch.delenv("A", raising=False)
    monkeypatch.setenv("B", "env-wins")
    resolved = env.setup_widgets(
        dbutils,
        {
            "A": {"default": "a-default", "label": "A"},
            "B": {"default": "b-default", "choices": ["b-default", "env-wins"]},
        },
    )
    assert resolved == {"A": "a-default", "B": "env-wins"}
    assert dbutils.widgets.declared["B"]["type"] == "dropdown"
    import os

    assert os.environ["A"] == "a-default"
    monkeypatch.delenv("A", raising=False)
