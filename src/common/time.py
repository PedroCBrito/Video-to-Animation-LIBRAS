"""Time helpers used by persisted pipeline contracts."""

from datetime import datetime, timezone


def utc_now() -> str:
    """Return an ISO-8601 timestamp with an explicit UTC offset."""
    return datetime.now(timezone.utc).isoformat()
