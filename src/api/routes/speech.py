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
from src.repositories.requirement_repository import RequirementRepository
from src.repositories.conflict_repository import ConflictRepository
from src.services.requirement.requirement_extractor import RequirementExtractorService
from src.services.requirement.requirement_thread_service import RequirementThreadService
from src.services.conflict.conflict_detector import ConflictDetectorService
from src.db.postgres import PostgresGateway
from src.core.config import load_speech_settings

router = APIRouter()

# Singletons for this router
_settings = load_speech_settings()
_gateway = PostgresGateway.from_env()
_azure_speech = AzureSpeechClient(_settings)
_meeting_repo = MeetingRepository(_gateway)
_req_repo = RequirementRepository(_gateway)
_conflict_repo = ConflictRepository(_gateway)
_transcription_service = TranscriptionService()
_req_extractor = RequirementExtractorService()
_conflict_detector = ConflictDetectorService()
_thread_service = RequirementThreadService(_gateway)


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
        "organization_id": user.get("organization_id"),
        "project_id": body.project_id,
        "host_id": user["id"],
        "title": body.name,
        "status": "active",
        "start_time": utc_now(),
    }
    
    _meeting_repo.save_meeting(meeting_data)
    _meeting_repo.add_participant(meeting_id, user["id"])
    _transcription_service.register_passcode(meeting_id, passcode)
    
    # In a real app, this link would point to your frontend domain
    invite_link = f"{_settings.frontend_base_url}/login?meetingId={meeting_id}&passcode={passcode}"
    
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
        
    _meeting_repo.add_participant(body.meeting_id, user["id"])

    return MeetingResponse(
        status="success",
        meeting_id=meeting["id"],
        project_id=meeting.get("project_id"),
        passcode=body.passcode,
        invite_link=f"{_settings.frontend_base_url}/login?meetingId={meeting['id']}&passcode={body.passcode}",
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
        # Mark the meeting as completed and set end_time
        _meeting_repo.end_meeting(meeting_id)
        
        captions = _transcription_service.get_captions(meeting_id)
        captions_dicts = [cap.model_dump() for cap in captions]
        mappings = _transcription_service.get_requirement_mappings(meeting_id)
        
        result = _meeting_repo.finalize_transcript(meeting_id, captions_dicts, mappings)
        if not result:
            # We don't raise 404 here, we just return success with empty result
            # because the meeting was still ended successfully.
            return {"status": "success", "data": {"transcript_id": None, "utterance_count": 0}}
        
        return {"status": "success", "data": result}
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.get("/meeting/{meeting_id}/requirements")
def get_meeting_requirements(
    meeting_id: str,
    user: dict = Depends(get_current_user)
):
    try:
        # Fetch all requirements (active, conflicted, discarded, etc.) for review
        requirements = _req_repo.get_all_for_conflict_check(meeting_id)
        return {"status": "success", "requirements": requirements}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/meeting/{meeting_id}/conflicts")
def get_meeting_conflicts(
    meeting_id: str,
    user: dict = Depends(get_current_user)
):
    try:
        conflicts = _conflict_repo.get_by_meeting(meeting_id)
        return {"status": "success", "conflicts": conflicts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/meeting/{meeting_id}/threads")
def get_meeting_threads(
    meeting_id: str,
    user: dict = Depends(get_current_user)
):
    try:
        threads = _thread_service.thread_repo.get_threads_by_meeting(meeting_id)
        return {"status": "success", "threads": threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from pydantic import BaseModel

class ResolutionItem(BaseModel):
    conflict_id: str
    resolution_type: str  # 'keep_a' | 'keep_b' | 'merge' | 'dismiss'
    merged_text: str | None = None

class EditedRequirementItem(BaseModel):
    requirement_id: str
    text: str

class FinalizeRequirementsRequest(BaseModel):
    resolutions: list[ResolutionItem]
    edited_requirements: list[EditedRequirementItem]


@router.post("/meeting/{meeting_id}/requirements/finalize")
def finalize_requirements(
    meeting_id: str,
    body: FinalizeRequirementsRequest,
    user: dict = Depends(get_current_user)
):
    try:
        # 1. Update any inline edited requirements
        for item in body.edited_requirements:
            _req_repo.update_status(item.requirement_id, "active")  # Reset/ensure active
            _gateway.update(
                _gateway.settings.requirements_table,
                {"requirement_text": item.text},
                eq={"id": item.requirement_id}
            )

        # 2. Process active resolutions
        conflicts = _conflict_repo.get_by_meeting(meeting_id)
        conflict_map = {c["id"]: c for c in conflicts}

        for res in body.resolutions:
            conflict = conflict_map.get(res.conflict_id)
            if not conflict:
                continue

            req_a_id = conflict["requirement_a_id"]
            req_b_id = conflict["requirement_b_id"]

            if res.resolution_type == "keep_a":
                _req_repo.update_status(req_a_id, "active")
                _req_repo.update_status(req_b_id, "discarded")
            elif res.resolution_type == "keep_b":
                _req_repo.update_status(req_a_id, "discarded")
                _req_repo.update_status(req_b_id, "active")
            elif res.resolution_type == "merge":
                _req_repo.update_status(req_a_id, "resolved_merged")
                _req_repo.update_status(req_b_id, "resolved_merged")
                # Save new merged requirement
                from src.models.requirement import Requirement
                import uuid
                merged_req = Requirement(
                    requirement_id=str(uuid.uuid4()),
                    meeting_id=meeting_id,
                    requirement_text=res.merged_text or "Merged Requirement",
                    requirement_type="functional",
                    status="active"
                )
                _req_repo.save([merged_req])
            elif res.resolution_type == "dismiss":
                _req_repo.update_status(req_a_id, "active")
                _req_repo.update_status(req_b_id, "active")

            # Remove resolved conflict entry
            _gateway.delete(_gateway.settings.conflicts_table, eq={"id": res.conflict_id})

        # 3. Clean up any remaining conflicted requirements that weren't addressed
        remaining = _req_repo.get_all_for_conflict_check(meeting_id)
        for req in remaining:
            if req["status"] == "conflicted":
                _req_repo.update_status(req["id"], "active")

        return {"status": "success", "message": "Requirements finalized successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

    # Initialize to None — set inside try block if Azure init succeeds
    recognizer = None
    push_stream = None
    try:
        speech_config = _azure_speech.get_speech_config()
        speech_config.speech_recognition_language = "en-US" # Explicitly set language
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
                
                print(f"[Azure] ✅ Final result from {speaker_label}: {text!r}")
                
                start_time = evt.result.offset / 10000000 if hasattr(evt.result, "offset") else None
                duration = evt.result.duration / 10000000 if hasattr(evt.result, "duration") else None
                end_time = (start_time + duration) if start_time is not None and duration is not None else None

                broadcast_data = {
                    "type": "transcription",
                    "data": {
                        "text": text,
                        "speaker_id": conn_id,
                        "speaker_name": speaker_label,
                        "is_final": True,
                        "timestamp": utc_now(),
                        "timestamp_start": start_time,
                        "timestamp_end": end_time
                    }
                }
                
                # Only enqueue for broadcast — push_caption runs in queue_worker
                # (asyncio loop) to avoid cross-thread lock contention.
                loop.call_soon_threadsafe(result_queue.put_nowait, broadcast_data)
            elif evt.result.reason == speechsdk.ResultReason.NoMatch:
                print(f"[Azure] ⚠️ NoMatch (could not recognize speech, possibly wrong language or just noise)")
            else:
                print(f"[Azure] ⚠️ Recognition reason: {evt.result.reason}")

        def handle_partial_result(evt):
            if evt.result.text:
                print(f"[Azure] 🔄 Partial from {speaker_label}: {evt.result.text!r}")
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

        def handle_canceled(evt):
            print(f"[Azure] ❌ Canceled: {evt.reason}")
            if evt.reason == speechsdk.CancellationReason.Error:
                print(f"[Azure] ❌ Error details: {evt.error_details}")

        recognizer.recognized.connect(handle_final_result)
        recognizer.recognizing.connect(handle_partial_result)
        recognizer.canceled.connect(handle_canceled)
        recognizer.start_continuous_recognition_async().get()
        print(f"[Azure] 🎙️ Recognizer started for {speaker_label} in meeting {meeting_id}")
        
    except Exception as e:
        print(f"[Azure] ❌ Transcription Service Error: {e}")
        recognizer = None
        push_stream = None

    # Background task to process the queue and broadcast to all clients
    async def queue_worker():
        try:
            while True:
                data = await result_queue.get()
                # Broadcast to all participants in this meeting
                for conn in _transcription_service.get_connections(meeting_id):
                    try: await conn.send_json(data)
                    except: pass
                # Persist final captions here — safe, runs in asyncio loop, not Azure thread
                # This avoids cross-thread _lock contention that deadlocks the Azure callback.
                if data.get("type") == "transcription" and data.get("data", {}).get("is_final"):
                    try:
                        caption = _transcription_service.push_caption(
                            meeting_id,
                            data["data"]["speaker_name"],
                            data["data"]["text"],
                            speaker_id=data["data"].get("speaker_id"),
                            timestamp_start=data["data"].get("timestamp_start"),
                            timestamp_end=data["data"].get("timestamp_end")
                        )
                        
                        # Background task to extract requirements from this utterance
                        async def extract_and_store(utterance_text: str, caption_id: str):
                            try:
                                # Get previous utterance for context
                                captions = _transcription_service.get_captions(meeting_id)
                                prev_text = captions[-2].text if len(captions) > 1 else ""

                                # Run extraction and classification in thread pool
                                requirements, label = await asyncio.to_thread(
                                    _req_extractor.extract,
                                    utterance_text,
                                    meeting_id,
                                    previous_utterance=prev_text,
                                    next_utterance=""
                                )

                                # Update caption type in transcription service
                                _transcription_service.update_caption_type(meeting_id, caption_id, label)

                                if not requirements:
                                    return
                                    
                                # Save requirements to DB
                                await asyncio.to_thread(_req_repo.save, requirements)
                                
                                # Generate embeddings
                                embeddings_data = []
                                mappings = []
                                req_embeddings: dict[str, list[float]] = {}
                                for req in requirements:
                                    emb = await asyncio.to_thread(_req_extractor.get_embedding, req.requirement_text)
                                    embeddings_data.append({
                                        "requirement_id": req.requirement_id,
                                        "embedding": emb
                                    })
                                    req_embeddings[req.requirement_id] = emb
                                    mappings.append({
                                        "requirement_id": req.requirement_id,
                                        "utterance_id": caption_id
                                    })
                                    
                                # Save embeddings to DB
                                await asyncio.to_thread(_req_repo.save_embeddings, embeddings_data)
                                
                                # Process requirements through Requirement Thread Manager (State Machine + Threading)
                                for req in requirements:
                                    emb = req_embeddings.get(req.requirement_id)
                                    await asyncio.to_thread(
                                        _thread_service.process_requirement,
                                        meeting_id,
                                        req.requirement_id,
                                        req.requirement_text,
                                        emb
                                    )

                                # Save mappings in memory until finalize_transcript
                                _transcription_service.add_requirement_mappings(meeting_id, mappings)
                                
                                # Broadcast extracted requirements to clients
                                req_payload = {
                                    "type": "requirements",
                                    "data": [r.model_dump() for r in requirements]
                                }
                                thread_signal = {"type": "THREAD_UPDATED", "data": {}}
                                for c in _transcription_service.get_connections(meeting_id):
                                    try:
                                        await c.send_json(req_payload)
                                        await c.send_json(thread_signal)
                                    except:
                                        pass
                                    
                                print(f"[Requirements] Extracted {len(requirements)} requirements from utterance.")
                                
                                # ── Conflict Detection ──────────────────────────────────────────
                                all_conflicts = []
                                for req in requirements:
                                    detected = await asyncio.to_thread(
                                        _conflict_detector.detect,
                                        req,
                                        _req_repo,
                                    )
                                    if detected:
                                        all_conflicts.extend(detected)
                                        # Mark the new requirement as conflicted
                                        await asyncio.to_thread(
                                            _req_repo.update_status, req.requirement_id, "conflicted"
                                        )
                                        # Mark each existing conflicting requirement accordingly
                                        for conflict in detected:
                                            other_id = conflict.requirement_b_id
                                            # Only mark the other req as conflicted if it isn't already
                                            await asyncio.to_thread(
                                                _req_repo.update_status, other_id, "conflicted"
                                            )
                                
                                if all_conflicts:
                                    await asyncio.to_thread(_conflict_repo.save, all_conflicts)
                                    
                                    conflict_payload = {
                                        "type": "conflicts",
                                        "data": [c.model_dump() for c in all_conflicts]
                                    }
                                    for c in _transcription_service.get_connections(meeting_id):
                                        try: await c.send_json(conflict_payload)
                                        except: pass
                                    
                                    print(f"[Conflicts] {len(all_conflicts)} conflict(s) detected and saved.")
                                
                            except Exception as ex:
                                print(f"[Requirements] Error during extraction: {ex}")
                                
                        # Fire and forget the extraction task
                        asyncio.create_task(extract_and_store(data["data"]["text"], caption.id))
                        
                    except ValueError:
                        pass  # Session already cleaned up — safe to ignore
                result_queue.task_done()
        except asyncio.CancelledError:
            pass

    worker_task = asyncio.create_task(queue_worker())

    # Main WebSocket Loop
    bytes_received = 0
    try:
        while True:
            msg = await websocket.receive()
            
            if msg.get("type") == "websocket.disconnect":
                break
            
            if msg.get("bytes") is not None:
                if recognizer and push_stream:
                    if bytes_received == 0:
                        print(f"[WS] 📡 FIRST audio chunk received from {speaker_label} ({len(msg['bytes'])} bytes)")
                    
                    push_stream.write(msg["bytes"])
                    
                    # Save a debug copy of the audio to disk to verify it's not silent
                    with open("debug_audio.pcm", "ab") as f:
                        f.write(msg["bytes"])

                    bytes_received += len(msg["bytes"])
                    
                    if bytes_received % 320000 < len(msg["bytes"]):  # print ~every 10 seconds of 16kHz audio
                        # Calculate rough volume peak to check for silence
                        import struct
                        shorts = struct.unpack(f"{len(msg['bytes'])//2}h", msg["bytes"])
                        max_vol = max(abs(s) for s in shorts) if shorts else 0
                        print(f"[WS] 📡 Audio received from {speaker_label}: {bytes_received} total bytes. Peak volume: {max_vol}")
                
            elif msg.get("text") is not None:
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
                stop_future = recognizer.stop_continuous_recognition_async()
                stop_future.get()   # Block until Azure flushes all buffered audio
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
                mappings = _transcription_service.get_requirement_mappings(meeting_id)
                _meeting_repo.finalize_transcript(meeting_id, captions_dicts, mappings)
            except ValueError:
                pass # Session not found
        else:
            # Otherwise, just notify the remaining people
            for conn in _transcription_service.get_connections(meeting_id):
                try: await conn.send_json({"type": "participants", "data": participants})
                except: pass
