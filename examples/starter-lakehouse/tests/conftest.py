"""Shared fakes: unit tests never need a Spark session or a workspace."""

from __future__ import annotations

from typing import Any

import pytest


class FakeWidgets:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.declared: dict[str, dict[str, Any]] = {}

    def get(self, name: str) -> str:
        return self.values[name]

    def text(self, name: str, default: str, label: str = "") -> None:
        self.declared[name] = {"type": "text", "default": default, "label": label}
        self.values.setdefault(name, default)

    def dropdown(self, name: str, default: str, choices: list[str], label: str = "") -> None:
        self.declared[name] = {"type": "dropdown", "default": default, "choices": choices, "label": label}
        self.values.setdefault(name, default)


class FakeTaskValues:
    def __init__(self) -> None:
        self.stored: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self.stored[key] = value

    def get(self, taskKey: str, key: str, default: Any = None, **_: Any) -> Any:
        return self.stored.get(key, default)


class FakeJobs:
    def __init__(self) -> None:
        self.taskValues = FakeTaskValues()


class FakeDbutils:
    def __init__(self) -> None:
        self.widgets = FakeWidgets()
        self.jobs = FakeJobs()


class FakeWriter:
    def __init__(self) -> None:
        self.format_used: str | None = None
        self.options: dict[str, str] = {}
        self.mode_used: str | None = None
        self.saved_as: str | None = None

    def format(self, fmt: str) -> FakeWriter:
        self.format_used = fmt
        return self

    def option(self, key: str, value: str) -> FakeWriter:
        self.options[key] = value
        return self

    def mode(self, mode: str) -> FakeWriter:
        self.mode_used = mode
        return self

    def saveAsTable(self, name: str) -> None:
        self.saved_as = name


class FakeColumn:
    def __init__(self, name: str) -> None:
        self.name = name
        self.cast_to: str | None = None

    def cast(self, data_type: str) -> FakeColumn:
        self.cast_to = data_type
        return self


class FakeDataFrame:
    def __init__(self, schema: Any = None, columns: list[str] | None = None) -> None:
        self.schema = schema
        self._columns = columns or ([f.name for f in schema.fields] if schema else [])
        self.write = FakeWriter()
        self.with_columns: dict[str, FakeColumn] = {}
        self.dropped: tuple[str, ...] = ()

    @property
    def columns(self) -> list[str]:
        return list(self._columns)

    def __getitem__(self, name: str) -> FakeColumn:
        return FakeColumn(name)

    def withColumn(self, name: str, col: FakeColumn) -> FakeDataFrame:
        self.with_columns[name] = col
        return self

    def drop(self, *names: str) -> FakeDataFrame:
        self.dropped = names
        return self


@pytest.fixture
def dbutils() -> FakeDbutils:
    return FakeDbutils()
