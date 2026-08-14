"""Threshold-driven QA: structured issues, a report gate, and task-value short-circuits.

Silent failure is the disease: a table that quietly shrinks or stops updating
with nothing downstream erroring. Checks here compare counts against the
thresholds recorded in ``tramat.yml`` (``conventions.qa``) and produce
structured issues; a report with any ERROR fails the gate loudly.

Task-value short-circuits let an upstream task (e.g. a fetcher that found
nothing new) tell downstream tasks to skip, without a failed run.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

#: mirrors conventions.qa.row_count_tolerance in tramat.yml
DEFAULT_ROW_COUNT_TOLERANCE = 0.05

SKIP_KEY = "tramat_skip"


@dataclass(frozen=True)
class Issue:
    """One structured QA finding."""

    table: str
    severity: str  # "ERROR" | "WARN" | "INFO"
    code: str
    message: str
    details: Mapping[str, object] | None = None


@dataclass
class QAReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "ERROR" for issue in self.issues)

    def summary(self) -> str:
        by_severity = {"ERROR": 0, "WARN": 0, "INFO": 0}
        for issue in self.issues:
            by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
        status = "PASS" if self.ok else "FAIL"
        return f"QA {status}: {by_severity['ERROR']} error(s), {by_severity['WARN']} warning(s), {by_severity['INFO']} info"

    def raise_if_failed(self) -> None:
        if not self.ok:
            errors = "; ".join(f"{i.table}:{i.code} {i.message}" for i in self.issues if i.severity == "ERROR")
            raise RuntimeError(f"{self.summary()} — {errors}")


def check_row_count(
    previous: int, current: int, table: str, *, tolerance: float = DEFAULT_ROW_COUNT_TOLERANCE
) -> Issue | None:
    """ERROR when a table shrinks beyond tolerance — the silent-failure classic."""
    if previous <= 0:
        return None
    drop = (previous - current) / previous
    if drop > tolerance:
        return Issue(
            table=table,
            severity="ERROR",
            code="ROW_COUNT_DROP",
            message=f"row count dropped {drop:.1%} ({previous} → {current}), tolerance {tolerance:.1%}",
            details={"previous": previous, "current": current, "tolerance": tolerance},
        )
    return None


def check_duplicates(duplicate_count: int, table: str, *, keys: Sequence[str] = ()) -> Issue | None:
    if duplicate_count > 0:
        return Issue(
            table=table,
            severity="ERROR",
            code="DUPLICATE_KEYS",
            message=f"{duplicate_count} duplicate row(s) for key ({', '.join(keys) or 'unspecified'})",
            details={"duplicates": duplicate_count, "keys": list(keys)},
        )
    return None


def check_nulls(null_counts: Mapping[str, int], table: str) -> list[Issue]:
    """ERROR per required column that contains nulls (pass counts for required columns only)."""
    return [
        Issue(
            table=table,
            severity="ERROR",
            code="NULLS_IN_REQUIRED",
            message=f"column {column!r} has {count} null(s)",
            details={"column": column, "nulls": count},
        )
        for column, count in null_counts.items()
        if count > 0
    ]


def check_columns(
    actual: Sequence[str], expected: Sequence[str], table: str, *, allow_extra: bool = True
) -> list[Issue]:
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    issues = []
    if missing:
        issues.append(
            Issue(
                table=table,
                severity="ERROR",
                code="MISSING_COLUMNS",
                message=f"missing columns: {', '.join(missing)}",
                details={"missing": missing},
            )
        )
    if unexpected and not allow_extra:
        issues.append(
            Issue(
                table=table,
                severity="WARN",
                code="UNEXPECTED_COLUMNS",
                message=f"unexpected columns: {', '.join(unexpected)}",
                details={"unexpected": unexpected},
            )
        )
    return issues


def run_checks(*findings: Issue | None | Iterable[Issue]) -> QAReport:
    """Flatten check results (single issues, lists, or Nones) into a report."""
    report = QAReport()
    for finding in findings:
        if finding is None:
            continue
        if isinstance(finding, Issue):
            report.issues.append(finding)
        else:
            report.issues.extend(finding)
    return report


def signal_skip(dbutils: Any, reason: str, *, key: str = SKIP_KEY) -> None:
    """Upstream: record that downstream tasks may skip (e.g. nothing new fetched)."""
    dbutils.jobs.taskValues.set(key=key, value=reason)


def should_skip(dbutils: Any, upstream_task: str, *, key: str = SKIP_KEY) -> str | None:
    """Downstream: the skip reason set by ``upstream_task``, or None to proceed."""
    try:
        value = dbutils.jobs.taskValues.get(taskKey=upstream_task, key=key, default=None)
    except Exception:
        return None
    return str(value) if value else None
