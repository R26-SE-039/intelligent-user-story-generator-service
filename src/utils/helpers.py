"""Common helper functions."""

from datetime import datetime, timezone

def utc_now() -> str:
    """Return the current UTC time as an ISO formatted string."""
    return datetime.now(timezone.utc).isoformat()
