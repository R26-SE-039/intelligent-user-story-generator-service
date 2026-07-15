"""Real-time session and chunking service."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4
import re

from src.models.meeting import CaptionLine
from src.models.transcript import Chunk, Transcript, Utterance
from src.utils.formatter import normalize_text
from src.utils.helpers import utc_now


class TranscriptionService:
    """Thread-safe in-memory store for voice sessions and transcription utilities."""

    def __init__(self) -> None:
        self._sessions: dict[str, list[CaptionLine]] = {}
        self._participants: dict[str, dict[str, str]] = {}  # meeting_id -> {conn_id: name}
        self._connections: dict[str, list[Any]] = {}  # meeting_id -> [websocket_objs]
        self._connections: dict[str, list[Any]] = {}  # meeting_id -> [websocket_objs]
        self._passcodes: dict[str, str] = {} # meeting_id -> passcode
        self._mappings: dict[str, list[dict[str, str]]] = {} # meeting_id -> list of mappings
        self._lock = Lock()

    def register_passcode(self, meeting_id: str, passcode: str) -> None:
        with self._lock:
            self._passcodes[meeting_id] = passcode

    def validate_passcode(self, meeting_id: str, passcode: str) -> bool:
        with self._lock:
            return self._passcodes.get(meeting_id) == passcode

    def create_session(self) -> str:
        session_id = f"voice-{uuid4()}"
        with self._lock:
            self._sessions[session_id] = []
        return session_id

    def stop_session(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._sessions:
                self._sessions.pop(session_id)
            if session_id in self._mappings:
                self._mappings.pop(session_id)

    def push_caption(self, session_id: str, speaker: str, text: str, speaker_id: str | None = None, timestamp_start: float | None = None, timestamp_end: float | None = None) -> CaptionLine:
        with self._lock:
            if session_id not in self._sessions:
                raise ValueError("Session not found")

            caption = CaptionLine(
                id=str(uuid4()),
                speaker=speaker,
                speaker_id=speaker_id,
                text=text,
                timestamp_start=timestamp_start,
                timestamp_end=timestamp_end,
                created_at=utc_now(),
            )
            self._sessions[session_id].append(caption)
            return caption

    def update_caption_type(self, session_id: str, caption_id: str, utterance_type: str) -> None:
        with self._lock:
            if session_id in self._sessions:
                for caption in self._sessions[session_id]:
                    if caption.id == caption_id:
                        caption.utterance_type = utterance_type
                        break

    def get_captions(self, session_id: str) -> list[CaptionLine]:
        with self._lock:
            captions = self._sessions.get(session_id)
            if captions is None:
                raise ValueError("Session not found")
            return list(captions)
            
    def add_requirement_mappings(self, meeting_id: str, mappings: list[dict[str, str]]) -> None:
        with self._lock:
            if meeting_id not in self._mappings:
                self._mappings[meeting_id] = []
            self._mappings[meeting_id].extend(mappings)
            
    def get_requirement_mappings(self, meeting_id: str) -> list[dict[str, str]]:
        with self._lock:
            return list(self._mappings.get(meeting_id, []))

    def add_participant(self, meeting_id: str, conn_id: str, name: str, websocket: Any):
        with self._lock:
            if meeting_id not in self._participants:
                self._participants[meeting_id] = {}
                self._connections[meeting_id] = []
                self._sessions[meeting_id] = []
            
            self._participants[meeting_id][conn_id] = name
            self._connections[meeting_id].append(websocket)
            return list(self._participants[meeting_id].values())

    def remove_participant(self, meeting_id: str, conn_id: str, websocket: Any):
        with self._lock:
            if meeting_id in self._participants:
                if conn_id in self._participants[meeting_id]:
                    self._participants[meeting_id].pop(conn_id)
                if websocket in self._connections[meeting_id]:
                    self._connections[meeting_id].remove(websocket)
                
                # Cleanup if empty
                if not self._participants[meeting_id]:
                    self._participants.pop(meeting_id)
                    self._connections.pop(meeting_id)
            
            return list(self._participants.get(meeting_id, {}).values())

    def get_participants(self, meeting_id: str) -> list[dict[str, str]]:
        with self._lock:
            participants_map = self._participants.get(meeting_id, {})
            return [{"id": k, "name": v} for k, v in participants_map.items()]

    def get_connections(self, meeting_id: str) -> list[Any]:
        with self._lock:
            return list(self._connections.get(meeting_id, []))

    # --- Preprocessing and chunking logic ---
    def preprocess_utterances(self, utterances: list[Utterance]) -> list[Utterance]:
        """Normalize utterance text and drop empty lines."""
        processed: list[Utterance] = []
        for utterance in utterances:
            normalized = normalize_text(utterance.text)
            if not normalized:
                continue
            processed.append(
                Utterance(
                    speaker=utterance.speaker,
                    text=normalized,
                    timestamp_start=utterance.timestamp_start,
                    timestamp_end=utterance.timestamp_end,
                )
            )
        return processed

    def chunk_transcript(
        self,
        transcript: Transcript,
        chunk_size_words: int,
        chunk_overlap_words: int,
    ) -> list[Chunk]:
        """Chunk transcript by utterance groups and carry metadata through each chunk."""
        utterances = self.preprocess_utterances(transcript.utterances)
        if not utterances:
            return []

        chunks: list[list[Utterance]] = []
        current: list[Utterance] = []
        current_words = 0

        for utterance in utterances:
            words = len(utterance.text.split())
            if current and current_words + words > chunk_size_words:
                chunks.append(current)
                overlap: list[Utterance] = []
                overlap_words = 0
                for existing in reversed(current):
                    overlap.insert(0, existing)
                    overlap_words += len(existing.text.split())
                    if overlap_words >= chunk_overlap_words:
                        break
                current = overlap.copy()
                current_words = sum(len(item.text.split()) for item in current)

            current.append(utterance)
            current_words += words

        if current:
            chunks.append(current)

        result: list[Chunk] = []
        for idx, group in enumerate(chunks):
            text = "\n".join(f"{u.speaker}: {u.text}" for u in group)
            speakers = sorted({u.speaker for u in group})
            timestamp_start = next((u.timestamp_start for u in group if u.timestamp_start is not None), None)
            timestamp_end = next((u.timestamp_end for u in reversed(group) if u.timestamp_end is not None), None)

            result.append(
                Chunk(
                    chunk_id=f"{transcript.transcript_id}-chunk-{idx}",
                    transcript_id=transcript.transcript_id,
                    chunk_index=idx,
                    text=text,
                    speakers=speakers,
                    timestamp_start=timestamp_start,
                    timestamp_end=timestamp_end,
                    metadata={
                        "source": transcript.source or "unknown",
                        "participant_count": len(transcript.participants),
                        "product_area": transcript.product_area or "unknown",
                    },
                )
            )

        return result

    def parse_raw_text(self, text: str, transcript_id: str) -> Transcript:
        """Parse raw text into a Transcript object, attempting to detect speakers."""
        lines = text.splitlines()
        utterances = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect "Speaker: Text" or "Speaker (Role): Text"
            match = re.match(r"^([^:]+):\s*(.*)$", line)
            if match:
                speaker, content = match.groups()
                utterances.append(Utterance(speaker=speaker.strip(), text=content.strip(), timestamp_start=0.0))
            else:
                # Append to last utterance if it's a continuation line
                if utterances:
                    utterances[-1].text += f" {line}"
                else:
                    utterances.append(Utterance(speaker="Unknown", text=line, timestamp_start=0.0))

        return Transcript(
            transcript_id=transcript_id,
            source="text_upload",
            utterances=utterances
        )
