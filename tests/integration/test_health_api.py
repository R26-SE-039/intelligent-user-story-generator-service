"""Integration tests for the GET /health endpoint."""

from __future__ import annotations

import pytest


class TestHealthEndpoint:
    """Tests for the /health liveness check."""

    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_ok_status(self, client):
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "ok"

    def test_health_returns_service_name(self, client):
        response = client.get("/health")
        data = response.json()
        assert "service" in data
        assert "intelligent-user-story-generator" in data["service"]

    def test_health_returns_environment_field(self, client):
        response = client.get("/health")
        data = response.json()
        assert "environment" in data
