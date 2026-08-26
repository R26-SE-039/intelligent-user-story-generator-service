"""Unit tests for MeetingRepository and RequirementRepository using a mocked gateway."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, call

import pytest

from src.repositories.meeting_repository import MeetingRepository
from src.repositories.requirement_repository import RequirementRepository
from src.models.requirement import Requirement


# ---------------------------------------------------------------------------
# MeetingRepository
# ---------------------------------------------------------------------------


class TestMeetingRepositorySaveMeeting:
    """save_meeting delegates correctly to the gateway."""

    def test_save_meeting_calls_upsert(self, mock_gateway):
        repo = MeetingRepository(mock_gateway)
        data = {"id": "meet-001", "title": "Sprint Planning"}
        repo.save_meeting(data)

        mock_gateway.upsert.assert_called_once_with(
            mock_gateway.settings.meetings_table,
            data,
            on_conflict="id",
        )

    def test_save_meeting_passes_all_fields(self, mock_gateway):
        repo = MeetingRepository(mock_gateway)
        data = {
            "id": "meet-001",
            "organization_id": "org-001",
            "project_id": "proj-001",
            "title": "Sprint Planning",
            "status": "completed",
        }
        repo.save_meeting(data)
        args, kwargs = mock_gateway.upsert.call_args
        # The data dictionary passed to upsert should match exactly
        assert args[1] == data


class TestMeetingRepositoryGetMeeting:
    """get_meeting returns the first result or None."""

    def test_get_meeting_returns_dict_when_found(self, mock_gateway):
        expected = {"id": "meet-001", "title": "Retro"}
        mock_gateway.select.return_value = [expected]
        repo = MeetingRepository(mock_gateway)

        result = repo.get_meeting("meet-001")
        assert result == expected
        mock_gateway.select.assert_called_once_with(
            mock_gateway.settings.meetings_table,
            eq={"id": "meet-001"},
        )

    def test_get_meeting_returns_none_when_not_found(self, mock_gateway):
        mock_gateway.select.return_value = []
        repo = MeetingRepository(mock_gateway)

        result = repo.get_meeting("nonexistent-id")
        assert result is None


# ---------------------------------------------------------------------------
# RequirementRepository
# ---------------------------------------------------------------------------


def _make_requirement(meeting_id: str = "meet-001") -> Requirement:
    return Requirement(
        requirement_id=str(uuid.uuid4()),
        meeting_id=meeting_id,
        requirement_text="The system shall allow users to log in.",
        requirement_type="functional",
        status="active",
    )


class TestRequirementRepositoryGetByMeeting:
    """get_by_meeting uses _get_connection directly with a psycopg2 cursor."""

    def _make_mock_connection(self, rows: list[dict]):
        """Return a mock connection context manager that yields rows on fetchall()."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_gateway_cm = MagicMock()
        mock_gateway_cm.__enter__ = MagicMock(return_value=mock_conn)
        mock_gateway_cm.__exit__ = MagicMock(return_value=False)
        return mock_gateway_cm

    def test_get_by_meeting_calls_get_connection(self, mock_gateway):
        rows = [{"id": "req-001", "requirement_text": "Login feature"}]
        mock_gateway._get_connection.return_value = self._make_mock_connection(rows)
        repo = RequirementRepository(mock_gateway)
        results = repo.get_by_meeting("meet-001")
        mock_gateway._get_connection.assert_called_once()

    def test_get_by_meeting_returns_list(self, mock_gateway):
        rows = [
            {"id": "req-001", "requirement_text": "Login"},
            {"id": "req-002", "requirement_text": "Register"},
        ]
        mock_gateway._get_connection.return_value = self._make_mock_connection(rows)
        repo = RequirementRepository(mock_gateway)
        results = repo.get_by_meeting("meet-001")
        assert isinstance(results, list)
        assert len(results) == 2

    def test_get_by_meeting_returns_empty_list_when_no_results(self, mock_gateway):
        mock_gateway._get_connection.return_value = self._make_mock_connection([])
        repo = RequirementRepository(mock_gateway)
        results = repo.get_by_meeting("meet-001")
        assert results == []


class TestRequirementRepositorySave:
    """save() upserts correctly for a list of Requirement objects."""

    def test_save_calls_upsert_with_rows(self, mock_gateway):
        repo = RequirementRepository(mock_gateway)
        req = _make_requirement()
        repo.save([req])

        mock_gateway.upsert.assert_called_once()
        call_args = mock_gateway.upsert.call_args
        rows = call_args[0][1]  # second positional arg is the data rows
        assert isinstance(rows, list)
        assert len(rows) == 1
        assert rows[0]["id"] == req.requirement_id

    def test_save_empty_list_does_not_call_upsert(self, mock_gateway):
        repo = RequirementRepository(mock_gateway)
        repo.save([])
        mock_gateway.upsert.assert_not_called()
