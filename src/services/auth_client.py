import httpx
import logging

LOGGER = logging.getLogger(__name__)

async def fetch_active_iteration(
    project_id: str,
    jwt_token: str,
    auth_service_url: str,
    timeout: float = 3.0,
) -> dict | None:
    """
    Call Auth Service GET /projects/{project_id}/iterations/active.
    Returns iteration dict or None on any failure (graceful degrade).
    Never raises — meeting must always be creatable.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{auth_service_url}/projects/{project_id}/iterations/active",
                headers={"Authorization": jwt_token},
            )
            if response.status_code == 200:
                return response.json()
            return None  # 404 = no active iteration, that's fine
    except Exception as e:
        LOGGER.warning(f"[AuthClient] Could not fetch active iteration: {e}")
        return None  # graceful degrade

async def fetch_project_config(
    project_id: str,
    jwt_token: str,
    auth_service_url: str,
    timeout: float = 3.0,
) -> dict | None:
    """
    Call Auth Service GET /projects/{project_id}/configuration.
    Returns config dict (with decrypted credentials) or None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{auth_service_url}/projects/{project_id}/configuration",
                headers={"Authorization": jwt_token},
            )
            if response.status_code == 200:
                return response.json()
            return None
    except Exception as e:
        LOGGER.warning(f"[AuthClient] Could not fetch project configuration: {e}")
        return None

