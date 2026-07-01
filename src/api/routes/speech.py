"""API routes for speech-to-text service."""

from typing import Any
import random
import string
import uuid
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
import azure.cognitiveservices.speech as speechsdk

from src.models.meeting import (
    MeetingCreateRequest,
    MeetingJoinRequest,
    MeetingResponse,
    CaptionLine
)
from src.api.dependencies import get_current_user
from src.utils.helpers import utc_now

from src.services.speech.transcription_service import TranscriptionService
from src.services.speech.azure_client import AzureSpeechClient
from src.repositories.meeting_repository import MeetingRepository
from src.db.postgres import PostgresGateway
from src.core.config import load_speech_settings

router = APIRouter()

# Singletons for this router
_settings = load_speech_settings()
_gateway = PostgresGateway.from_env()
_azure_speech = AzureSpeechClient(_settings)
_meeting_repo = MeetingRepository(_gateway)
_transcription_service = TranscriptionService()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "speech-to-text"}

@router.post("/meeting/create", response_model=MeetingResponse)
def create_meeting(
    body: MeetingCreateRequest,
    user: dict = Depends(get_current_user)
) -> MeetingResponse:
    meeting_id = str(uuid.uuid4())
    passcode = ''.join(random.choices(string.digits, k=6))
    
    meeting_data = {
        "id": meeting_id,
        "organization_id": None,
        "project_id": body.project_id,
        "host_id": user["id"],
        "title": body.name,
        "status": "active",
        "created_at": utc_now(),
    }
    
    _meeting_repo.save_meeting(meeting_data)
    _transcription_service.register_passcode(meeting_id, passcode)
    
    # In a real app, this link would point to your frontend domain
    invite_link = f"http://localhost:5173/login?meetingId={meeting_id}&passcode={passcode}"
    
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
    user: dict = Depends(get_current_user)
) -> MeetingResponse:
    meeting = _meeting_repo.get_meeting(body.meeting_id)
    
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
        
    if not _transcription_service.validate_passcode(body.meeting_id, body.passcode):
        raise HTTPException(status_code=401, detail="Invalid passcode")
        
    return MeetingResponse(
        status="success",
        meeting_id=meeting["id"],
        project_id=meeting.get("project_id"),
        passcode=body.passcode,
        invite_link=f"http://localhost:5173/login?meetingId={meeting['id']}&passcode={body.passcode}",
        name=meeting["title"]
    )

@router.get("/meeting/{meeting_id}/chats")
def get_meeting_chats(
    meeting_id: str,
    user: dict = Depends(get_current_user)
):
    chats = _meeting_repo.get_chats(meeting_id)
    return {"status": "success", "chats": chats}

@router.get("/meeting/{meeting_id}/transcript")
def get_meeting_transcript(
    meeting_id: str,
    user: dict = Depends(get_current_user)
):
    try:
        transcript = _transcription_service.get_captions(meeting_id)
        return {"status": "success", "transcript": transcript}
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")

@router.post("/meeting/{meeting_id}/analyze")
def analyze_meeting(
    meeting_id: str,
    body: dict,
    user: dict = Depends(get_current_user)
):
    analysis_type = body.get("type", "summary")
    
    if analysis_type == "summary":
        return {
            "status": "success",
            "data": "The meeting focused on the migration of session management to the Voice Service. The team discussed the benefits of centralizing real-time state and decided to proceed with the refactor."
        }
    elif analysis_type == "action_items":
        return {
            "status": "success",
            "data": [
                "Update Postgres schema to include meeting_chats table.",
                "Refactor frontend dashboard to use Azure Real-time hooks."
            ]
        }
    
    return {"status": "error", "message": "Unknown analysis type"}

@router.post("/meeting/{meeting_id}/finalize")
def finalize_meeting(
    meeting_id: str,
    user: dict = Depends(get_current_user)
):
    try:
        captions = _transcription_service.get_captions(meeting_id)
        captions_dicts = [cap.model_dump() for cap in captions]
        result = _meeting_repo.finalize_transcript(meeting_id, captions_dicts)
        if not result:
            raise HTTPException(status_code=404, detail="No captions found for this meeting to finalize.")
        
        return {"status": "success", "data": result}
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")

@router.websocket("/ws/{meeting_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    meeting_id: str,
    name: str = "Anonymous",
    role: str | None = None,
    user_id: str | None = None
):
    await websocket.accept()
    conn_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    
    # Combine name and role for the label
    speaker_label = f"{name} ({role})" if role else name
    
    # Add to store
    _transcription_service.add_participant(meeting_id, conn_id, name, websocket)
    
    # Broadcast current participants
    participants = _transcription_service.get_participants(meeting_id)
    for conn in _transcription_service.get_connections(meeting_id):
        try: await conn.send_json({"type": "participants", "data": participants})
        except: pass

    # Queue for thread-safe communication from Azure callback to this async loop
    result_queue = asyncio.Queue()

    # Azure Speech Real-time Integration
    try:
        speech_config = _azure_speech.get_speech_config()
        push_stream = _azure_speech.create_push_stream()
        audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
        
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, 
            audio_config=audio_config
        )

        def handle_final_result(evt):
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                text = evt.result.text
                if not text: return
                
                broadcast_data = {
                    "type": "transcription",
                    "data": {
                        "text": text,
                        "speaker_id": conn_id,
                        "speaker_name": speaker_label,
                        "is_final": True,
                        "timestamp": utc_now()
                    }
                }
                
                # Schedule broadcast and persistence
                loop.call_soon_threadsafe(result_queue.put_nowait, broadcast_data)
                _transcription_service.push_caption(meeting_id, speaker_label, text)

        def handle_partial_result(evt):
            broadcast_data = {
                "type": "transcription",
                "data": {
                    "text": evt.result.text,
                    "speaker_id": conn_id,
                    "speaker_name": speaker_label,
                    "is_final": False
                }
            }
            loop.call_soon_threadsafe(result_queue.put_nowait, broadcast_data)

        recognizer.recognized.connect(handle_final_result)
        recognizer.recognizing.connect(handle_partial_result)
        recognizer.start_continuous_recognition_async()
        
    except Exception as e:
        print(f"[Azure] ❌ Transcription Service Error: {e}")
        recognizer = None

    # Background task to process the queue and broadcast to all clients
    async def queue_worker():
        try:
            while True:
                data = await result_queue.get()
                # Broadcast to all participants in this meeting
                for conn in _transcription_service.get_connections(meeting_id):
                    try: await conn.send_json(data)
                    except: pass
                result_queue.task_done()
        except asyncio.CancelledError:
            pass

    worker_task = asyncio.create_task(queue_worker())

    # Main WebSocket Loop
    try:
        while True:
            msg = await websocket.receive()
            
            if "bytes" in msg:
                if recognizer:
                    push_stream.write(msg["bytes"])
                
            elif "text" in msg:
                data = json.loads(msg["text"])
                if data.get("type") == "chat":
                    text = data.get("text", "")
                    sender_id = user_id or str(uuid.uuid4())
                    _meeting_repo.save_chat(meeting_id, sender_id, text)
                    for conn in _transcription_service.get_connections(meeting_id):
                        try:
                            await conn.send_json({
                                "type": "chat",
                                "data": {
                                    "sender": data.get("sender", name),
                                    "text": text,
                                    "timestamp": utc_now()
                                }
                            })
                        except: pass
                elif data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        # Cleanup
        worker_task.cancel()
        if recognizer:
            try: 
                recognizer.stop_continuous_recognition_async()
                push_stream.close()
            except: pass
        
        _transcription_service.remove_participant(meeting_id, conn_id, websocket)
        participants = _transcription_service.get_participants(meeting_id)
        
        # If this was the last person, auto-finalize the transcript
        if not participants:
            print(f"[Meeting] {meeting_id} is empty. Auto-finalizing transcript...")
            try:
                captions = _transcription_service.get_captions(meeting_id)
                captions_dicts = [cap.model_dump() for cap in captions]
                _meeting_repo.finalize_transcript(meeting_id, captions_dicts)
            except ValueError:
                pass # Session not found
        else:
            # Otherwise, just notify the remaining people
            for conn in _transcription_service.get_connections(meeting_id):
                try: await conn.send_json({"type": "participants", "data": participants})
                except: pass
