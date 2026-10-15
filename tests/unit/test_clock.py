import pathlib
import re
from datetime import UTC, datetime, timedelta

import pytest

from app.clock import Clock, format_utc


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


def test_only_clock_module_reads_system_time() -> None:
    pattern = re.compile(r"datetime\.(now|utcnow)\(|date\.today\(|time\.time\(")
    offenders = [
        str(p)
        for p in pathlib.Path("app").rglob("*.py")
        if p.name != "clock.py" and pattern.search(p.read_text())
    ]
    assert offenders == []
