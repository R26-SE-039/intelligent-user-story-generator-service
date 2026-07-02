"""Security and authentication helpers."""

# pyrefly: ignore [missing-import]
import jwt
from typing import Any

def decode_jwt(token: str, secret: str) -> dict[str, Any] | None:
    """Decode and validate a JWT token."""
    try:
        decoded = jwt.decode(token, secret, algorithms=["HS256"])
        user_id = decoded.get("userId") or decoded.get("sub")
        if not user_id:
            return None

        return {
            "id": user_id,
            "email": decoded.get("email", "unknown@example.com"),
            "role": decoded.get("role", "user"),
            "organization_id": decoded.get("organizationId"),
        }
    except Exception as e:
        print(f"Auth error: {e}")
        return None
