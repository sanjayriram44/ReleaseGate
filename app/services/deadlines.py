"""CRA reporting deadlines (REQ-06): pure functions of stored timestamps and the clock's now.

Nothing here is stored or scheduled; every read recomputes deadline_at and status. All datetimes
are timezone-aware UTC (app.clock.parse_utc), compared exactly with 0 s tolerance (AC-07).
Rules: CLAUDE.md §6.4 and docs/decisions.md (Q2, Q3). Needs a team member's review (§14.2).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

Stage = Literal["early_warning", "vulnerability_notification", "final_report"]
Classification = Literal["mandatory", "voluntary"]
Status = Literal["pending", "met", "overdue", "not_applicable"]

STAGES: tuple[Stage, ...] = ("early_warning", "vulnerability_notification", "final_report")

EARLY_WARNING = timedelta(hours=24)
VULNERABILITY_NOTIFICATION = timedelta(hours=72)
FINAL_REPORT = timedelta(days=14)


@dataclass(frozen=True)
class Deadline:
    deadline_at: datetime | None
    submitted_at: datetime | None
    status: Status


def deadline_at(
    stage: str,
    classification: str,
    awareness_at: datetime,
    fix_available_at: datetime | None,
) -> datetime | None:
    """None when the stage has no deadline: a voluntary case, or a final report before a fix."""
    if classification != "mandatory":
        return None
    if stage == "early_warning":
        return awareness_at + EARLY_WARNING
    if stage == "vulnerability_notification":
        return awareness_at + VULNERABILITY_NOTIFICATION
    if stage == "final_report":
        return fix_available_at + FINAL_REPORT if fix_available_at is not None else None
    raise ValueError(f"unknown stage {stage!r}")


def status(deadline: datetime | None, submitted_at: datetime | None, now: datetime) -> Status:
    """met if submitted at or before the deadline; a late submission stays overdue (Q2).
    Unsubmitted: pending while now <= deadline, overdue after it."""
    if deadline is None:
        return "not_applicable"
    if submitted_at is not None:
        return "met" if submitted_at <= deadline else "overdue"
    return "pending" if now <= deadline else "overdue"


def compute(
    classification: str,
    awareness_at: datetime,
    fix_available_at: datetime | None,
    submissions: Mapping[str, datetime],
    now: datetime,
) -> dict[Stage, Deadline]:
    """Every stage's deadline, submission time and status at `now`."""
    out: dict[Stage, Deadline] = {}
    for stage in STAGES:
        due = deadline_at(stage, classification, awareness_at, fix_available_at)
        submitted = submissions.get(stage)
        out[stage] = Deadline(due, submitted, status(due, submitted, now))
    return out
