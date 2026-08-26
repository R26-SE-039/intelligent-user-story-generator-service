"""Unit tests for src.core.security.decode_jwt."""

from __future__ import annotations

import time

import jwt
import pytest

from src.core.security import decode_jwt

SECRET = "test-unit-secret"


def _make_token(payload: dict, secret: str = SECRET, algorithm: str = "HS256") -> str:
    return jwt.encode(payload, secret, algorithm=algorithm)


class TestDecodeJwtValidToken:
    """Tests for well-formed, valid tokens."""

    def test_returns_user_info_with_userId_claim(self):
        payload = {
            "userId": "user-001",
            "email": "alice@example.com",
            "role": "BA",
            "organizationId": "org-abc",
            "exp": int(time.time()) + 3600,
        }
        result = decode_jwt(_make_token(payload), SECRET)
        assert result is not None
        assert result["id"] == "user-001"
        assert result["email"] == "alice@example.com"
        assert result["role"] == "BA"
        assert result["organization_id"] == "org-abc"

    def test_falls_back_to_sub_claim_when_userId_missing(self):
        payload = {
            "sub": "user-via-sub",
            "exp": int(time.time()) + 3600,
        }
        result = decode_jwt(_make_token(payload), SECRET)
        assert result is not None
        assert result["id"] == "user-via-sub"

    def test_defaults_email_when_missing(self):
        payload = {"userId": "u1", "exp": int(time.time()) + 3600}
        result = decode_jwt(_make_token(payload), SECRET)
        assert result["email"] == "unknown@example.com"

    def test_defaults_role_to_user_when_missing(self):
        payload = {"userId": "u1", "exp": int(time.time()) + 3600}
        result = decode_jwt(_make_token(payload), SECRET)
        assert result["role"] == "user"


class TestDecodeJwtInvalidToken:
    """Tests for malformed or rejected tokens."""

    def test_returns_none_for_wrong_secret(self):
        payload = {"userId": "u1", "exp": int(time.time()) + 3600}
        token = _make_token(payload, secret="correct-secret")
        result = decode_jwt(token, "wrong-secret")
        assert result is None

    def test_returns_none_for_expired_token(self):
        payload = {"userId": "u1", "exp": int(time.time()) - 10}
        token = _make_token(payload)
        result = decode_jwt(token, SECRET)
        assert result is None

    def test_returns_none_for_garbage_string(self):
        result = decode_jwt("not.a.valid.jwt", SECRET)
        assert result is None

    def test_returns_none_when_userId_and_sub_both_missing(self):
        payload = {"email": "noone@example.com", "exp": int(time.time()) + 3600}
        token = _make_token(payload)
        result = decode_jwt(token, SECRET)
        assert result is None
