from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
import logging

from src.services.jira_service import JiraService
from src.services.auth_client import fetch_project_config
from src.api.dependencies import get_settings
from src.core.config import Settings

LOGGER = logging.getLogger(__name__)
router = APIRouter()

class TestConnectionRequest(BaseModel):
    jiraUrl: str
    jiraEmail: str
    jiraApiToken: str

class SyncStoryItem(BaseModel):
    story_id: str
    title: str
    story: str
    acceptance_criteria: list[str]
    quality_score: float = 100.0
    status: str = "ready"

class SyncStoriesRequest(BaseModel):
    projectId: str
    iterationName: str
    stories: list[SyncStoryItem]

@router.post("/test-connection")
def test_connection(request: TestConnectionRequest):
    try:
        service = JiraService(
            jira_url=request.jiraUrl,
            jira_email=request.jiraEmail,
            jira_api_token=request.jiraApiToken
        )
        service.test_connection()
        return {"success": True, "message": "Successfully connected to Atlassian Jira Cloud!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/sync-stories")
async def sync_stories(
    request: SyncStoriesRequest,
    authorization: str | None = Header(None),
    settings: Settings = Depends(get_settings)
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    # Fetch configuration from Auth Service
    config = await fetch_project_config(
        project_id=request.projectId,
        jwt_token=authorization,
        auth_service_url=settings.auth_service_url
    )

    if not config:
        raise HTTPException(status_code=404, detail="Project configuration not found in Auth Service")

    jira_url = config.get("jira_url")
    jira_email = config.get("jira_email")
    jira_api_token = config.get("jira_api_token")
    project_key = config.get("jira_project_key")

    if not jira_url or not jira_email or not jira_api_token or not project_key:
        raise HTTPException(
            status_code=400, 
            detail="Jira integration is not fully configured for this project"
        )

    try:
        service = JiraService(
            jira_url=jira_url,
            jira_email=jira_email,
            jira_api_token=jira_api_token
        )
        
        # Get or create Epic for the Iteration Name
        epic_key = service.get_or_create_epic(project_key, request.iterationName)

        # Prepare stories payload
        stories_list = [s.model_dump() for s in request.stories]

        # Export stories
        results = service.export_user_stories(
            project_key=project_key,
            stories=stories_list,
            epic_key=epic_key
        )

        return {
            "success": True,
            "epic_key": epic_key,
            "results": results
        }
    except Exception as e:
        LOGGER.exception("Jira synchronization failed")
        raise HTTPException(status_code=500, detail=f"Jira sync failed: {str(e)}")
