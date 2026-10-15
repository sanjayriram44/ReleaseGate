from datetime import UTC, date, datetime

from app.clock import Clock
from app.services.releases import support_status


def _status(end: date, now: datetime) -> str:
    clock = Clock()
    clock.set(now)
    return support_status(end, clock)


END = date(2026, 6, 15)


def test_day_before_end_is_supported() -> None:
    assert _status(END, datetime(2026, 6, 14, 12, tzinfo=UTC)) == "supported"


def test_start_of_end_day_is_supported() -> None:
    assert _status(END, datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)) == "supported"


def test_last_second_of_end_day_is_supported() -> None:
    assert _status(END, datetime(2026, 6, 15, 23, 59, 59, tzinfo=UTC)) == "supported"


def test_first_second_after_end_day_is_unsupported() -> None:
    assert _status(END, datetime(2026, 6, 16, 0, 0, 0, tzinfo=UTC)) == "unsupported"
