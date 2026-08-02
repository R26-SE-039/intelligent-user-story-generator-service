"""API routes for speech-to-text and live meeting voice services."""

from typing import Optional
import random
import string
import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket

from src.models.meeting import (
    MeetingCreateRequest,
    MeetingJoinRequest,
    MeetingResponse,
)
from src.models.schemas import FinalizeRequirementsRequest
from src.models.conflict import ConflictResolutionRequest
from src.api.dependencies import (
    get_current_user,
    get_speech_settings,
    get_meeting_repo,
    get_requirement_repo,
    get_transcript_repo,
    get_conflict_repo,
    get_transcription_service,
    get_requirement_extractor,
    get_requirement_thread_service,
    get_live_meeting_service,
)
from src.core.config import SpeechServiceSettings
from src.utils.helpers import utc_now
from src.services.speech.transcription_service import TranscriptionService
from src.services.speech.live_meeting_service import LiveMeetingService
from src.services.speech.live_meeting_coordinator import LiveMeetingCoordinator
from src.repositories.meeting_repository import MeetingRepository
from src.repositories.requirement_repository import RequirementRepository
from src.repositories.transcript_repository import TranscriptRepository
from src.repositories.conflict_repository import ConflictRepository
from src.services.requirement.requirement_thread_service import RequirementThreadService
from src.core.logger import get_logger

LOGGER = get_logger(__name__)

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "speech-to-text"}


@router.post("/meeting/create", response_model=MeetingResponse)
def create_meeting(
    body: MeetingCreateRequest,
    user: dict = Depends(get_current_user),
    meeting_repo: MeetingRepository = Depends(get_meeting_repo),
    transcription_service: TranscriptionService = Depends(get_transcription_service),
    settings: SpeechServiceSettings = Depends(get_speech_settings),
) -> MeetingResponse:
    meeting_id = str(uuid.uuid4())
    passcode = ''.join(random.choices(string.digits, k=6))
    
    meeting_data = {
        "id": meeting_id,
        "organization_id": user.get("organization_id"),
        "project_id": body.project_id,
        "host_id": user["id"],
        "title": body.name,
        "status": "active",
        "start_time": utc_now(),
    }
    
    meeting_repo.save_meeting(meeting_data)
    meeting_repo.add_participant(meeting_id, user["id"])
    transcription_service.init_session(meeting_id)
    transcription_service.register_passcode(meeting_id, passcode)
    
    invite_link = f"{settings.frontend_base_url}/login?meetingId={meeting_id}&passcode={passcode}"
    
    return MeetingResponse(
        status="success",
        meeting_id=meeting_id,
        project_id=body.project_id,
        passcode=passcode,
        invite_link=invite_link,
        name=body.name
    )


@router.post("/meeting/join", response_model=MeetingResponse)
def join_meeting(
    body: MeetingJoinRequest,
    user: dict = Depends(get_current_user),
    meeting_repo: MeetingRepository = Depends(get_meeting_repo),
    transcription_service: TranscriptionService = Depends(get_transcription_service),
    settings: SpeechServiceSettings = Depends(get_speech_settings),
) -> MeetingResponse:
    meeting = meeting_repo.get_meeting(body.meeting_id)
    
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
        
    if not transcription_service.validate_passcode(body.meeting_id, body.passcode):
        raise HTTPException(status_code=401, detail="Invalid passcode")
        
    meeting_repo.add_participant(body.meeting_id, user["id"])

    return MeetingResponse(
        status="success",
        meeting_id=meeting["id"],
        project_id=meeting.get("project_id"),
        passcode=body.passcode,
        invite_link=f"{settings.frontend_base_url}/login?meetingId={meeting['id']}&passcode={body.passcode}",
        name=meeting["title"]
    )


@router.get("/meeting/{meeting_id}/chats")
def get_meeting_chats(
    meeting_id: str,
    user: dict = Depends(get_current_user),
    meeting_repo: MeetingRepository = Depends(get_meeting_repo),
):
    chats = meeting_repo.get_chats(meeting_id)
    return {"status": "success", "chats": chats}


@router.get("/meeting/{meeting_id}/transcript")
def get_meeting_transcript(
    meeting_id: str,
    user: dict = Depends(get_current_user),
    transcription_service: TranscriptionService = Depends(get_transcription_service),
    transcript_repo: TranscriptRepository = Depends(get_transcript_repo),
):
    try:
        transcript = transcription_service.get_captions(meeting_id)
        if transcript:
            return {"status": "success", "transcript": transcript}
    except ValueError:
        pass

    try:
        captions = transcript_repo.get_captions_by_meeting(meeting_id)
        return {"status": "success", "transcript": captions}
    except Exception as e:
        LOGGER.warning("[SpeechRoute] DB fallback transcript fetch failed: %s", e)

    return {"status": "success", "transcript": []}



@router.post("/meeting/{meeting_id}/finalize")
def finalize_meeting(
    meeting_id: str,
    user: dict = Depends(get_current_user),
    meeting_repo: MeetingRepository = Depends(get_meeting_repo),
    transcription_service: TranscriptionService = Depends(get_transcription_service),
    live_meeting_service: LiveMeetingService = Depends(get_live_meeting_service),
):
    try:
        meeting_repo.end_meeting(meeting_id)
        
        try:
            captions = transcription_service.get_captions(meeting_id)
            captions_dicts = [cap.model_dump() for cap in captions]
            mappings = transcription_service.get_requirement_mappings(meeting_id)
            result = meeting_repo.finalize_transcript(meeting_id, captions_dicts, mappings)
        except ValueError:
            result = {"transcript_id": None, "utterance_count": 0}

        transcript_id = (result or {}).get("transcript_id")
        if transcript_id:
            live_meeting_service.embed_and_store_utterances(transcript_id)

        transcription_service.stop_session(meeting_id)
        
        return {"status": "success", "data": result or {"transcript_id": None, "utterance_count": 0}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/meeting/{meeting_id}/requirements")
def get_meeting_requirements(
    meeting_id: str,
    user: dict = Depends(get_current_user),
    req_repo: RequirementRepository = Depends(get_requirement_repo),
    thread_service: RequirementThreadService = Depends(get_requirement_thread_service),
):
    try:
        requirements = req_repo.get_all_for_conflict_check(meeting_id)
        threads = thread_service.thread_repo.get_threads_by_meeting(meeting_id)
        return {"status": "success", "requirements": requirements, "threads": threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/meeting/{meeting_id}/conflicts")
def get_meeting_conflicts(
    meeting_id: str,
    user: dict = Depends(get_current_user),
    conflict_repo: ConflictRepository = Depends(get_conflict_repo),
):
    try:
        conflicts = conflict_repo.get_by_meeting(meeting_id)
        return {"status": "success", "conflicts": conflicts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/meeting/{meeting_id}/threads")
def get_meeting_threads(
    meeting_id: str,
    user: dict = Depends(get_current_user),
    thread_service: RequirementThreadService = Depends(get_requirement_thread_service),
):
    try:
        threads = thread_service.thread_repo.get_threads_by_meeting(meeting_id)
        return {"status": "success", "threads": threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/meeting/{meeting_id}/requirements/finalize")
def finalize_requirements(
    meeting_id: str,
    body: FinalizeRequirementsRequest,
    user: dict = Depends(get_current_user),
    thread_service: RequirementThreadService = Depends(get_requirement_thread_service),
    req_repo: RequirementRepository = Depends(get_requirement_repo),
    conflict_repo: ConflictRepository = Depends(get_conflict_repo),
    req_extractor = Depends(get_requirement_extractor),
):
    try:
        user_id = user.get("id") if user else None
        thread_service.finalize_requirements(
            meeting_id=meeting_id,
            edited_threads=body.edited_threads,
            edited_requirements=body.edited_requirements,
            resolutions=body.resolutions,
            req_repo=req_repo,
            conflict_repo=conflict_repo,
            req_extractor=req_extractor,
            user_id=user_id,
        )
        return {"status": "success", "message": "Requirements finalized successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/meeting/{meeting_id}/conflicts/{conflict_id}/resolve")
def resolve_meeting_conflict(
    meeting_id: str,
    conflict_id: str,
    body: ConflictResolutionRequest,
    user: dict = Depends(get_current_user),
    thread_service: RequirementThreadService = Depends(get_requirement_thread_service),
    req_repo: RequirementRepository = Depends(get_requirement_repo),
    conflict_repo: ConflictRepository = Depends(get_conflict_repo),
    req_extractor = Depends(get_requirement_extractor),
):
    """
    BA Conflict Resolution Endpoint:
      - 1-Click Apply LLM Suggestion, Keep A/B, Manual Edit, Duplicate handling, or Dismiss.
      - Automatically re-embeds updated text into pgvector requirement_embeddings table.
      - Updates target/competing requirement statuses ('active', 'superseded', 'duplicate', 'discarded').
      - Logs audit trail in conflicts table (resolved_by, resolved_at, previous_texts).
      - Instantly returns updated active requirements and active conflicts lists for UI update.
    """
    try:
        user_id = body.user_id or (user.get("id") if user else None)
        result = thread_service.resolve_single_conflict(
            conflict_id=conflict_id,
            resolution_type=body.resolution_type,
            req_repo=req_repo,
            conflict_repo=conflict_repo,
            req_extractor=req_extractor,
            edited_text_a=body.edited_text_a,
            edited_text_b=body.edited_text_b,
            merged_text=body.merged_text,
            user_id=user_id,
        )
        refreshed_reqs = req_repo.get_all_for_conflict_check(meeting_id)
        refreshed_conflicts = conflict_repo.get_by_meeting(meeting_id, status="active")
        return {
            "status": "success",
            "message": "Conflict resolved successfully",
            "result": result,
            "requirements": refreshed_reqs,
            "conflicts": refreshed_conflicts,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        LOGGER.exception("[ConflictResolution] Resolution failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Conflict Resolution Failed: {str(exc)}")


@router.get("/project/{project_id}/conflicts")
def get_project_conflicts(
    project_id: str,
    status: str | None = "active",
    user: dict = Depends(get_current_user),
    conflict_repo: ConflictRepository = Depends(get_conflict_repo),
):
    """Fetch all conflicts across all meetings in a project for the BA Dashboard."""
    try:
        conflicts = conflict_repo.get_by_project(project_id, status=status)
        return {"status": "success", "project_id": project_id, "conflicts": conflicts}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



@router.websocket("/ws/{meeting_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    meeting_id: str,
    name: str = "Anonymous",
    role: str | None = None,
    user_id: str | None = None
):
    """Real-time meeting voice & transcription WebSocket endpoint."""
    coordinator: LiveMeetingCoordinator = websocket.app.state.meeting_coordinator
    await coordinator.handle_websocket_session(
        websocket=websocket,
        meeting_id=meeting_id,
        name=name,
        role=role,
        user_id=user_id,
    )
