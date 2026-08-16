"""Live meeting real-time speech processing service.

Handles async requirement extraction, classification, embedding generation,
thread grouping, conflict detection, and client broadcasting for active meeting sessions.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.repositories.conflict_repository import ConflictRepository
from src.repositories.requirement_repository import RequirementRepository
from src.repositories.transcript_repository import TranscriptRepository
from src.services.conflict.conflict_detector import ConflictDetectorService
from src.services.requirement.requirement_extractor import RequirementExtractorService
from src.services.requirement.requirement_thread_service import RequirementThreadService
from src.services.speech.transcription_service import TranscriptionService

LOGGER = logging.getLogger(__name__)


from src.repositories.meeting_repository import MeetingRepository

class LiveMeetingService:
    """Service orchestrating real-time requirement extraction and broadcasting during active meetings."""

    def __init__(
        self,
        transcription_service: TranscriptionService,
        req_extractor: RequirementExtractorService,
        req_repo: RequirementRepository,
        conflict_detector: ConflictDetectorService,
        conflict_repo: ConflictRepository,
        thread_service: RequirementThreadService,
        transcript_repo: TranscriptRepository,
        meeting_repo: MeetingRepository | None = None,
    ) -> None:
        self.transcription_service = transcription_service
        self.req_extractor = req_extractor
        self.req_repo = req_repo
        self.conflict_detector = conflict_detector
        self.conflict_repo = conflict_repo
        self.thread_service = thread_service
        self.transcript_repo = transcript_repo
        self.meeting_repo = meeting_repo

    async def process_utterance(
        self,
        meeting_id: str,
        utterance_text: str,
        caption_id: str,
    ) -> None:
        """Asynchronously extract requirements, generate embeddings, update threads,
        detect conflicts, and broadcast updates to meeting websocket clients.
        """
        try:
            # 1. Get previous utterance for context
            captions = self.transcription_service.get_captions(meeting_id)
            prev_text = captions[-2].text if len(captions) > 1 else ""

            # 2. Run requirement extraction and classification in thread pool
            requirements, label = await asyncio.to_thread(
                self.req_extractor.extract,
                utterance_text,
                meeting_id,
                previous_utterance=prev_text,
                next_utterance="",
            )

            # Update caption type in memory
            self.transcription_service.update_caption_type(meeting_id, caption_id, label)

            if not requirements:
                return

            # 3. Save raw requirements to DB
            await asyncio.to_thread(self.req_repo.save, requirements)

            # 4. Generate embeddings
            embeddings_data = []
            mappings = []
            req_embeddings: dict[str, list[float]] = {}
            for req in requirements:
                emb = await asyncio.to_thread(self.req_extractor.get_embedding, req.requirement_text)
                embeddings_data.append({
                    "requirement_id": req.requirement_id,
                    "embedding": emb
                })
                req_embeddings[req.requirement_id] = emb
                mappings.append({
                    "requirement_id": req.requirement_id,
                    "utterance_id": caption_id
                })

            await asyncio.to_thread(self.req_repo.save_embeddings, embeddings_data)

            # 5. Process requirements through Requirement Thread Manager
            for req in requirements:
                emb = req_embeddings.get(req.requirement_id)
                await asyncio.to_thread(
                    self.thread_service.process_requirement,
                    meeting_id,
                    req.requirement_id,
                    req.requirement_text,
                    emb
                )

            # Save mappings in memory until finalize_transcript
            self.transcription_service.add_requirement_mappings(meeting_id, mappings)

            # Broadcast extracted requirements to clients
            req_payload = {
                "type": "requirements",
                "data": [r.model_dump() for r in requirements]
            }
            thread_signal = {"type": "THREAD_UPDATED", "data": {}}
            for c in self.transcription_service.get_connections(meeting_id):
                try:
                    await c.send_json(req_payload)
                    await c.send_json(thread_signal)
                except Exception:
                    pass

            LOGGER.info("[LiveMeetingService] Extracted %d requirement(s) from utterance.", len(requirements))

            # 6. Conflict Detection (Project-Wide Vector Search)
            project_id = None
            if self.meeting_repo:
                try:
                    meeting = await asyncio.to_thread(self.meeting_repo.get_meeting, meeting_id)
                    project_id = meeting.get("project_id") if meeting else None
                except Exception as e:
                    LOGGER.warning("[LiveMeetingService] Failed to fetch project_id for meeting %s: %s", meeting_id, e)

            all_conflicts = []
            for req in requirements:
                emb = req_embeddings.get(req.requirement_id)
                detected = await asyncio.to_thread(
                    self.conflict_detector.detect,
                    req,
                    self.req_repo,
                    project_id=project_id,
                    embedding=emb,
                )
                if detected:
                    all_conflicts.extend(detected)
                    for conflict in detected:
                        expl = (conflict.explanation or "").lower()
                        is_dup = (
                            conflict.conflict_type == "duplicate"
                            or "duplicate" in expl
                            or "identical" in expl
                            or "same behavior" in expl
                            or "same intent" in expl
                        )
                        if is_dup:
                            conflict.conflict_type = "duplicate"
                            await asyncio.to_thread(
                                self.req_repo.mark_as_duplicate,
                                conflict.requirement_a_id,
                                duplicate_of_id=conflict.requirement_b_id,
                            )
                        else:
                            await asyncio.to_thread(
                                self.req_repo.update_status, conflict.requirement_a_id, "conflicted"
                            )
                            await asyncio.to_thread(
                                self.req_repo.update_status, conflict.requirement_b_id, "conflicted"
                            )

            logical_conflicts = [
                c for c in all_conflicts 
                if c.conflict_type != "duplicate"
                and not any(k in (c.explanation or "").lower() for k in ["duplicate", "identical", "same behavior", "same intent"])
            ]
            if logical_conflicts:
                await asyncio.to_thread(self.conflict_repo.save, logical_conflicts)
                conflict_payload = {
                    "type": "conflicts",
                    "data": [c.model_dump() for c in logical_conflicts]
                }
                for c in self.transcription_service.get_connections(meeting_id):
                    try:
                        await c.send_json(conflict_payload)
                    except Exception:
                        pass

                LOGGER.info("[LiveMeetingService] %d conflict(s) detected and saved.", len(all_conflicts))

        except Exception as ex:
            LOGGER.warning("[LiveMeetingService] Error during extraction: %s", ex)

    def embed_and_store_utterances(self, transcript_id: str) -> None:
        """Generate Gemini vector embeddings for all utterances of a transcript and persist them.

        Called synchronously inside meeting finalization.
        """
        try:
            utterances = self.transcript_repo.get_utterances_by_transcript(transcript_id)
            if not utterances:
                LOGGER.info("[LiveMeetingService] No utterances found for transcript %s — skipping.", transcript_id)
                return

            embeddings_data = []
            for utt in utterances:
                text = (utt.get("utterance_text") or "").strip()
                if not text:
                    continue
                emb = self.req_extractor.get_embedding(text)
                embeddings_data.append({
                    "utterance_id": str(utt["id"]),
                    "embedding": emb,
                })

            self.transcript_repo.save_utterance_embeddings(embeddings_data)
            LOGGER.info("[LiveMeetingService] Stored %d utterance embedding(s) for transcript %s.", len(embeddings_data), transcript_id)
        except Exception as exc:
            LOGGER.warning("[LiveMeetingService] Failed to embed utterances for transcript %s: %s", transcript_id, exc)
