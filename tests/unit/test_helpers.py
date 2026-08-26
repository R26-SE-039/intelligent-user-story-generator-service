"""Unit tests for src.utils.helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from src.utils.helpers import utc_now


class TestUtcNow:
    """Tests for the utc_now() helper function."""

    def test_returns_string(self):
        result = utc_now()
        assert isinstance(result, str)

    def test_is_valid_iso_format(self):
        result = utc_now()
        # datetime.fromisoformat() parses ISO 8601 strings (Python 3.7+)
        parsed = datetime.fromisoformat(result)
        assert parsed is not None

    def test_is_timezone_aware(self):
        result = utc_now()
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None

    def test_is_utc_timezone(self):
        result = utc_now()
        parsed = datetime.fromisoformat(result)
        # UTC offset should be 0
        assert parsed.utcoffset().total_seconds() == 0

    def test_successive_calls_are_monotonically_non_decreasing(self):
        first = datetime.fromisoformat(utc_now())
        second = datetime.fromisoformat(utc_now())
        assert second >= first
