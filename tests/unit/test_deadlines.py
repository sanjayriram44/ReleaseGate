"""Deadline math (REQ-06, CLAUDE.md §6.4; decisions Q2/Q3). Needs a team member's review."""

from datetime import UTC, datetime, timedelta

import pytest

from app.clock import parse_utc
from app.services.deadlines import Deadline, compute, deadline_at, status

SEC = timedelta(seconds=1)
MICRO = timedelta(microseconds=1)


def utc(text: str) -> datetime:
    return parse_utc(text)


AWARE = utc("2026-11-01T10:00:00Z")
EW = utc("2026-11-02T10:00:00Z")  # awareness + 24 h
VN = utc("2026-11-04T10:00:00Z")  # awareness + 72 h


def test_mandatory_deadlines_without_fix() -> None:
    assert deadline_at("early_warning", "mandatory", AWARE, None) == EW
    assert deadline_at("vulnerability_notification", "mandatory", AWARE, None) == VN
    assert deadline_at("final_report", "mandatory", AWARE, None) is None


def test_final_report_is_fix_plus_14_days() -> None:
    fix = utc("2026-11-03T12:34:56Z")
    assert deadline_at("final_report", "mandatory", AWARE, fix) == utc("2026-11-17T12:34:56Z")


def test_voluntary_has_no_deadlines_even_with_a_fix() -> None:
    fix = utc("2026-11-03T00:00:00Z")
    for stage in ("early_warning", "vulnerability_notification", "final_report"):
        assert deadline_at(stage, "voluntary", AWARE, fix) is None


@pytest.mark.parametrize(
    ("now", "want"),
    [(EW - SEC, "pending"), (EW, "pending"), (EW + MICRO, "overdue"), (EW + SEC, "overdue")],
)
def test_unsubmitted_status_around_the_deadline(now: datetime, want: str) -> None:
    assert status(EW, None, now) == want


@pytest.mark.parametrize(
    ("submitted", "want"),
    [(EW - SEC, "met"), (EW, "met"), (EW + MICRO, "overdue"), (EW + SEC, "overdue")],
)
def test_submitted_status_ignores_now(submitted: datetime, want: str) -> None:
    for now in (EW - timedelta(hours=1), EW, EW + timedelta(days=30)):
        assert status(EW, submitted, now) == want


def test_no_deadline_is_not_applicable() -> None:
    assert status(None, None, AWARE) == "not_applicable"


def test_month_and_year_rollover() -> None:
    aware = utc("2026-12-31T23:30:00Z")
    fix = utc("2026-12-25T00:00:00Z")
    assert deadline_at("early_warning", "mandatory", aware, None) == utc("2027-01-01T23:30:00Z")
    assert deadline_at("vulnerability_notification", "mandatory", aware, None) == utc(
        "2027-01-03T23:30:00Z"
    )
    assert deadline_at("final_report", "mandatory", aware, fix) == utc("2027-01-08T00:00:00Z")


def test_leap_day_counts_as_a_day() -> None:
    aware = utc("2028-02-28T12:00:00Z")
    assert deadline_at("vulnerability_notification", "mandatory", aware, None) == utc(
        "2028-03-02T12:00:00Z"
    )


def test_fractional_seconds_are_kept() -> None:
    aware = utc("2026-11-01T10:00:00.500000Z")
    ew = deadline_at("early_warning", "mandatory", aware, None)
    assert ew == utc("2026-11-02T10:00:00.500000Z")
    assert status(ew, utc("2026-11-02T10:00:00.500000Z"), ew) == "met"
    assert status(ew, utc("2026-11-02T10:00:00.500001Z"), ew) == "overdue"


def test_offset_inputs_give_the_same_deadlines() -> None:
    aware = utc("2026-11-01T12:00:00+02:00")
    assert aware == AWARE
    assert deadline_at("early_warning", "mandatory", aware, None) == EW


def test_compute_all_stages() -> None:
    fix = utc("2026-11-03T00:00:00Z")
    got = compute("mandatory", AWARE, fix, {"early_warning": EW}, now=VN + SEC)
    assert got == {
        "early_warning": Deadline(EW, EW, "met"),
        "vulnerability_notification": Deadline(VN, None, "overdue"),
        "final_report": Deadline(utc("2026-11-17T00:00:00Z"), None, "pending"),
    }
    assert all(d.deadline_at is None or d.deadline_at.tzinfo is UTC for d in got.values())


def test_compute_voluntary() -> None:
    got = compute("voluntary", AWARE, None, {}, now=AWARE + timedelta(days=100))
    assert {stage: d.status for stage, d in got.items()} == {
        "early_warning": "not_applicable",
        "vulnerability_notification": "not_applicable",
        "final_report": "not_applicable",
    }


def test_ac07_scenario() -> None:
    """AC-07: early warning exactly at +24 h is met; at 72 h + 1 s with no notification it is
    overdue; a final report 13 days after the fix is met."""
    fix = utc("2026-11-03T08:00:00Z")
    subs = {"early_warning": EW, "final_report": fix + timedelta(days=13)}
    got = compute("mandatory", AWARE, fix, subs, now=AWARE + timedelta(hours=72) + SEC)
    assert got["early_warning"].status == "met"
    assert got["vulnerability_notification"].status == "overdue"
    assert got["final_report"].status == "met"
