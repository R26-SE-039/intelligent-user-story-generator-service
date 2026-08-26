"""Integration tests for the Jira API endpoints.

Route under test:
  POST /api/v1/jira/sync-single   — mocked JiraService, no live Jira needed
  POST /api/v1/jira/test-connection
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestJiraTestConnectionEndpoint:
    """POST /api/v1/jira/test-connection"""

    def test_test_connection_succeeds_with_valid_credentials(self, client):
        mock_service = MagicMock()
        mock_service.test_connection.return_value = True

        with patch(
            "src.api.routes.jira.JiraService",
            return_value=mock_service,
        ):
            response = client.post(
                "/api/v1/jira/test-connection",
                json={
                    "jiraUrl": "https://example.atlassian.net",
                    "jiraEmail": "admin@example.com",
                    "jiraApiToken": "test-token-abc123",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_test_connection_returns_400_on_failure(self, client):
        mock_service = MagicMock()
        mock_service.test_connection.side_effect = Exception("Invalid credentials")

        with patch(
            "src.api.routes.jira.JiraService",
            return_value=mock_service,
        ):
            response = client.post(
                "/api/v1/jira/test-connection",
                json={
                    "jiraUrl": "https://bad-url.atlassian.net",
                    "jiraEmail": "user@example.com",
                    "jiraApiToken": "wrong-token",
                },
            )

        assert response.status_code == 400


class TestJiraSyncStoriesEndpoint:
    """POST /api/v1/jira/sync-stories requires Authorization header."""

    def test_sync_stories_returns_401_without_auth(self, client):
        response = client.post(
            "/api/v1/jira/sync-stories",
            json={
                "projectId": "proj-001",
                "iterationName": "Sprint 1",
                "stories": [],
            },
        )
        assert response.status_code == 401

    def test_sync_stories_returns_404_when_project_config_not_found(self, client, mock_auth_headers):
        """When fetch_project_config returns None, respond with 404."""
        with patch(
            "src.api.routes.jira.fetch_project_config",
            return_value=None,
        ) as mock_fetch:
            # Make the coroutine return None
            import asyncio
            mock_fetch.return_value = None

            # We need to mock the async function
            async def _mock_fetch(*args, **kwargs):
                return None

            with patch("src.api.routes.jira.fetch_project_config", side_effect=_mock_fetch):
                response = client.post(
                    "/api/v1/jira/sync-stories",
                    json={
                        "projectId": "proj-001",
                        "iterationName": "Sprint 1",
                        "stories": [],
                    },
                    headers=mock_auth_headers,
                )

        assert response.status_code == 404

    def test_sync_stories_succeeds_with_mocked_jira(self, client, mock_auth_headers):
        """Full happy-path: config fetched, JiraService syncs stories successfully."""
        mock_config = {
            "jira_url": "https://example.atlassian.net",
            "jira_email": "admin@example.com",
            "jira_api_token": "tok-abc",
            "jira_project_key": "TEST",
        }

        mock_jira_service = MagicMock()
        mock_jira_service.get_or_create_epic.return_value = "TEST-1"
        mock_jira_service.export_user_stories.return_value = [
            {"story_id": "story-001", "jira_key": "TEST-2", "success": True}
        ]

        async def _mock_fetch(*args, **kwargs):
            return mock_config

        with (
            patch("src.api.routes.jira.fetch_project_config", side_effect=_mock_fetch),
            patch("src.api.routes.jira.JiraService", return_value=mock_jira_service),
        ):
            response = client.post(
                "/api/v1/jira/sync-stories",
                json={
                    "projectId": "proj-001",
                    "iterationName": "Sprint 1",
                    "stories": [
                        {
                            "story_id": "story-001",
                            "title": "User Login",
                            "story": "As a user, I want to log in, so that I can access my dashboard.",
                            "acceptance_criteria": ["Given... When... Then..."],
                            "quality_score": 85.0,
                            "status": "ready",
                        }
                    ],
                },
                headers=mock_auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "epic_key" in data
        assert "results" in data
