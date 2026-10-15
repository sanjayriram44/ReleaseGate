"""The single source of "now" for the whole app. Nothing else may call datetime.now()."""

import threading
from datetime import UTC, datetime


def format_utc(dt: datetime) -> str:
    """ISO 8601 UTC with a trailing Z, e.g. 2026-01-01T00:00:00Z."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Clock:
    def __init__(self) -> None:
        self._override: datetime | None = None
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            if self._override is not None:
                return self._override
        return datetime.now(UTC)

    def set(self, dt: datetime) -> None:
        if dt.tzinfo is None:
            raise ValueError("clock time must be timezone-aware")
        with self._lock:
            self._override = dt.astimezone(UTC)

    def reset(self) -> None:
        with self._lock:
            self._override = None
