"""Security and authentication helpers."""

import jwt
from typing import Any

def decode_jwt(token: str, secret: str) -> dict[str, Any] | None:
    """Decode and validate a JWT token."""
    try:
        decoded = jwt.decode(token, secret, algorithms=["HS256"])
        if not decoded.get("sub"):
            return None

        return {
            "id": decoded["sub"],
            "email": decoded.get("email", "unknown@example.com"),
            "role": decoded.get("role", "user"),
        }
    except Exception as e:
        print(f"Auth error: {e}")
        return None
