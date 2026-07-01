"""API Dependencies shared across routers."""

from typing import Any
from fastapi import Header, HTTPException

from src.core.config import Settings
from src.core.security import decode_jwt

def get_current_user(authorization: str | None = Header(None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing authentication token")
    
    token = authorization.replace("Bearer ", "")
    settings = Settings()
    
    user = decode_jwt(token, settings.auth_secret)
    if not user:
        raise HTTPException(status_code=401, detail="User not found or token expired")
    return user
