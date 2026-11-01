import pathlib
import re
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.clock import Clock, format_utc, parse_utc
from app.errors import ApiError


def test_override_and_reset() -> None:
    clock = Clock()
    fixed = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    clock.set(fixed)
    assert clock.now() == fixed
    clock.reset()
    assert abs(clock.now() - datetime.now(UTC)) < timedelta(seconds=5)


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValueError):
        Clock().set(datetime(2026, 1, 1))


def test_format_utc_uses_z_suffix() -> None:
    assert format_utc(datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)) == "2026-03-04T05:06:07Z"


def test_format_utc_keeps_microseconds_when_present() -> None:
    dt = datetime(2026, 11, 1, 23, 59, 59, 100000, tzinfo=UTC)
    assert format_utc(dt) == "2026-11-01T23:59:59.100000Z"


def test_format_utc_converts_offsets() -> None:
    plus2 = timezone(timedelta(hours=2))
    assert format_utc(datetime(2026, 1, 1, 1, 0, tzinfo=plus2)) == "2025-12-31T23:00:00Z"


# Team 2's inputs from the Phase 3 cross-team run (CLAUDE.md §4 item 3).
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-01T12:00:00Z", "2026-11-01T12:00:00Z"),
        ("2026-11-01T12:00:00-00:00", "2026-11-01T12:00:00Z"),
        ("2026-11-01T12:00:00+02:00", "2026-11-01T10:00:00Z"),
        ("2026-11-01T12:00:00-05:30", "2026-11-01T17:30:00Z"),
        ("2026-11-01T12:00:00+05:45", "2026-11-01T06:15:00Z"),
        ("2026-11-01T12:00:00+23:59", "2026-10-31T12:01:00Z"),
        ("2026-11-01T12:00:00-23:59", "2026-11-02T11:59:00Z"),
        ("2026-11-01T23:59:59.1Z", "2026-11-01T23:59:59.100000Z"),
        ("2026-11-01T12:00:00.123456+02:00", "2026-11-01T10:00:00.123456Z"),
        ("2026-11-01T12:00:00.123456789Z", "2026-11-01T12:00:00.123456Z"),
        ("2026-12-31T23:30:00-01:00", "2027-01-01T00:30:00Z"),
    ],
)
def test_parse_utc_accepts_z_or_offset(value: str, expected: str) -> None:
    dt = parse_utc(value)
    assert dt.tzinfo is UTC
    assert format_utc(dt) == expected


@pytest.mark.parametrize(
    "value",
    [
        "2026-11-01T12:00:00",  # no zone
        "2026-11-01T12:00:00.5",
        "2026-11-01 12:00:00Z",
        "2026-11-01T12:00:00z",
        "2026-11-01T12:00:00+0200",
        "2026-11-01T12:00:00+24:00",
        "2026-11-01T12:00:00+02:60",
        "2026-02-30T00:00:00Z",
        "2026-11-01T12:00Z",
        "2026-11-01",
        "",
    ],
)
def test_parse_utc_rejects(value: str) -> None:
    with pytest.raises(ApiError) as exc:
        parse_utc(value, "awareness_at")
    assert exc.value.status == 400 and exc.value.code == "INVALID_REQUEST"
    assert exc.value.message.startswith("awareness_at ")


def test_only_clock_module_reads_system_time() -> None:
    pattern = re.compile(r"datetime\.(now|utcnow)\(|date\.today\(|time\.time\(")
    offenders = [
        str(p)
        for p in pathlib.Path("app").rglob("*.py")
        if p.name != "clock.py" and pattern.search(p.read_text())
    ]
    assert offenders == []


@pytest.mark.parametrize(
    "value",
    [
        "9999-12-31T00:00:00Z",  # + 14 days would overflow
        "9999-12-18T00:00:00Z",
        "0001-01-01T00:00:00+01:00",  # converting to UTC would underflow
    ],
)
def test_parse_utc_rejects_timestamps_at_the_calendar_limits(value: str) -> None:
    with pytest.raises(ApiError) as exc:
        parse_utc(value, "awareness_at")
    assert exc.value.status == 400
    assert exc.value.message.startswith("awareness_at is out of range")


def test_parse_utc_accepts_the_last_supported_moment() -> None:
    assert format_utc(parse_utc("9999-12-17T23:59:59Z")) == "9999-12-17T23:59:59Z"
    assert format_utc(parse_utc("0001-01-01T00:00:00Z")) == "0001-01-01T00:00:00Z"
