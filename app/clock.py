"""The single source of "now" for the whole app, and the one timestamp parser and formatter.

Nothing else may call datetime.now(), and every timestamp read or written goes through
parse_utc / format_utc.
"""

import re
import threading
from datetime import UTC, datetime, timedelta

from app.errors import ApiError

# Deadlines add up to 14 days (CRA final report), so later timestamps would overflow datetime.
LATEST = datetime.max.replace(tzinfo=UTC) - timedelta(days=14)

# Date, time, optional fraction, then Z or a numeric offset up to ±23:59 (fromisoformat alone
# would read +02:60 as +03:00). A timestamp with no zone is rejected.
_TIMESTAMP = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)


def parse_utc(value: str, field: str = "now") -> datetime:
    """An ISO 8601 timestamp with Z or a UTC offset, converted to UTC; else ApiError(400).

    Fractional seconds are kept, truncated beyond microseconds.
    """
    match = _TIMESTAMP.match(value)
    if not match:
        raise ApiError(
            400,
            "INVALID_REQUEST",
            f"{field} must be a timestamp with Z or a UTC offset, e.g. 2026-11-01T12:00:00Z",
        )
    base, fraction, zone = match.groups()
    micros = f".{fraction[:6].ljust(6, '0')}" if fraction else ""
    try:
        dt = datetime.fromisoformat(base + micros + ("+00:00" if zone == "Z" else zone))
    except ValueError as exc:
        raise ApiError(400, "INVALID_REQUEST", f"{field} is not a valid timestamp") from exc
    try:
        utc = dt.astimezone(UTC)
    except OverflowError:  # e.g. 0001-01-01T00:00:00+01:00 is before year 1 in UTC
        utc = None
    if utc is None or utc > LATEST:
        raise ApiError(
            400,
            "INVALID_REQUEST",
            f"{field} is out of range (0001-01-01T00:00:00Z to {format_utc(LATEST)})",
        )
    return utc


def format_utc(dt: datetime) -> str:
    """ISO 8601 UTC with a trailing Z: whole seconds when there is no fraction, else six-digit
    microseconds, e.g. 2026-01-01T00:00:00Z or 2026-01-01T00:00:00.100000Z."""
    # isoformat, not strftime: glibc's %Y doesn't zero-pad, so on Linux year 1 came out as "1-".
    utc = dt.astimezone(UTC).replace(tzinfo=None)
    return utc.isoformat(timespec="microseconds" if utc.microsecond else "seconds") + "Z"


class Clock:
    def __init__(self) -> None:
        self._override: datetime | None = None
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            if self._override is not None:
                return self._override
        return datetime.now(UTC)

    def overridden(self) -> bool:
        """True while the test clock has set the time."""
        with self._lock:
            return self._override is not None

    def set(self, dt: datetime) -> None:
        if dt.tzinfo is None:
            raise ValueError("clock time must be timezone-aware")
        with self._lock:
            self._override = dt.astimezone(UTC)

    def reset(self) -> None:
        with self._lock:
            self._override = None
