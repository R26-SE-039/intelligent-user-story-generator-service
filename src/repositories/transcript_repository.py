"""Repository for transcript data."""

from __future__ import annotations
import logging
from uuid import uuid4

from src.db.postgres import PostgresGateway
from src.models.transcript import Chunk, Transcript
from src.utils.helpers import utc_now

LOGGER = logging.getLogger(__name__)


class TranscriptRepository:
    def __init__(self, gateway: PostgresGateway) -> None:
        self._gateway = gateway

    def save(self, transcript: Transcript) -> None:
        # Save Transcript
        self._gateway.upsert(
            self._gateway.settings.transcripts_table,
            {
                "id": transcript.transcript_id,
                "meeting_id": transcript.meeting_id,
                "created_at": utc_now(),
            },
            on_conflict="id"
        )

        # Save Utterances
        utterance_rows = []
        for index, item in enumerate(transcript.utterances):
            utterance_rows.append(
                {
                    "id": str(uuid4()), # We generate a UUID for the utterance
                    "transcript_id": transcript.transcript_id,
                    "speaker_id": item.speaker_id,
                    "speaker_name": item.speaker,
                    "utterance_text": item.text,
                    "start_time": item.timestamp_start,
                    "end_time": item.timestamp_end,
                    "confidence_score": getattr(item, "confidence_score", None),
                    "utterance_type": getattr(item, "utterance_type", None)
                }
            )

        if utterance_rows:
            self._gateway.upsert(
                self._gateway.settings.transcript_utterances_table, 
                utterance_rows, 
                on_conflict="id"
            )

    def get_captions_by_meeting(self, meeting_id: str) -> list[dict]:
        """Fetch all transcript utterance captions for a meeting from DB fallback."""
        try:
            transcripts_db = self._gateway.select("transcripts", eq={"meeting_id": meeting_id})
            if not transcripts_db:
                return []
            t_id = transcripts_db[0]["id"]
            utterances_db = self._gateway.select("transcript_utterances", eq={"transcript_id": t_id})
            captions = []
            for u in utterances_db:
                captions.append({
                    "id": u.get("id"),
                    "speaker": u.get("speaker_name", "Unknown"),
                    "speaker_id": str(u.get("speaker_id")) if u.get("speaker_id") else None,
                    "text": u.get("utterance_text", ""),
                    "timestamp_start": float(u["start_time"]) if u.get("start_time") is not None else None,
                    "timestamp_end": float(u["end_time"]) if u.get("end_time") is not None else None,
                    "created_at": str(u.get("created_at")) if u.get("created_at") else None,
                    "utterance_type": u.get("utterance_type")
                })
            return captions
        except Exception as exc:
            LOGGER.warning("[TranscriptRepository] get_captions_by_meeting failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Utterance embedding methods (pgvector RAG)
    # ------------------------------------------------------------------

    def get_utterances_by_transcript(self, transcript_id: str) -> list[dict]:
        """Fetch id and text for every utterance in a transcript.

        Used at finalize_meeting time to generate and store embeddings.
        """
        try:
            from psycopg2.extras import RealDictCursor
            with self._gateway._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        'SELECT id, utterance_text FROM transcript_utterances '
                        'WHERE transcript_id = %s',
                        (transcript_id,)
                    )
                    return [dict(row) for row in cur.fetchall()]
        except Exception as exc:
            LOGGER.warning(
                "[TranscriptRepository] get_utterances_by_transcript failed: %s", exc
            )
            return []

    def save_utterance_embeddings(self, embeddings_data: list[dict]) -> None:
        """Persist Gemini vector embeddings for utterances to pgvector.

        Args:
            embeddings_data: List of {"utterance_id": str, "embedding": list[float]}
        """
        if not embeddings_data:
            return
        rows = []
        for data in embeddings_data:
            vec_str = "[" + ",".join(str(x) for x in data["embedding"]) + "]"
            rows.append({
                "utterance_id": data["utterance_id"],
                "embedding": vec_str,
            })
        self._gateway.upsert("utterance_embeddings", rows, on_conflict="utterance_id")

    def find_relevant_utterances(
        self,
        query_embedding: list[float],
        meeting_id: str,
        top_k: int = 8,
    ) -> list[dict]:
        """Retrieve the top-K utterances most semantically similar to a query.

        Uses pgvector cosine distance (<=>) to rank utterances belonging to
        the given meeting.  Returns rows ordered from most to least relevant.

        Args:
            query_embedding: 3072-dim Gemini embedding of the query text.
            meeting_id:      Filter utterances to this meeting only.
            top_k:           Maximum number of utterances to return.

        Returns:
            List of dicts with keys: id, transcript_id, utterance_text,
            speaker_name, start_time, end_time, utterance_type, distance.
        """
        vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        query = """
            SELECT
                tu.id,
                tu.transcript_id,
                tu.utterance_text,
                tu.speaker_name,
                tu.start_time,
                tu.end_time,
                tu.utterance_type,
                (ue.embedding <=> %s::vector) AS distance
            FROM utterance_embeddings ue
            JOIN transcript_utterances tu ON tu.id = ue.utterance_id
            JOIN transcripts           t  ON t.id  = tu.transcript_id
            WHERE t.meeting_id = %s
              AND tu.utterance_text IS NOT NULL
              AND tu.utterance_text != ''
            ORDER BY distance ASC
            LIMIT %s;
        """
        try:
            from psycopg2.extras import RealDictCursor
            with self._gateway._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (vec_str, meeting_id, top_k))
                    return [dict(row) for row in cur.fetchall()]
        except Exception as exc:
            LOGGER.warning(
                "[TranscriptRepository] find_relevant_utterances failed: %s", exc
            )
            return []

    def get_requirement_utterances_by_meeting(
        self,
        meeting_id: str,
        limit: int = 15,
    ) -> list[dict]:
        """Fetch utterances belonging to a meeting directly from DB as a fallback.

        Used when vector embeddings are missing or pgvector search returns no results.
        Returns rows ordered by start_time.
        """
        query = """
            SELECT
                tu.id,
                tu.transcript_id,
                tu.utterance_text,
                tu.speaker_name,
                tu.start_time,
                tu.end_time,
                tu.utterance_type
            FROM transcript_utterances tu
            JOIN transcripts t ON t.id = tu.transcript_id
            WHERE t.meeting_id = %s
              AND tu.utterance_text IS NOT NULL
              AND tu.utterance_text != ''
            ORDER BY tu.start_time ASC NULLS LAST
            LIMIT %s;
        """
        try:
            from psycopg2.extras import RealDictCursor
            with self._gateway._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (meeting_id, limit))
                    return [dict(row) for row in cur.fetchall()]
        except Exception as exc:
            LOGGER.warning(
                "[TranscriptRepository] get_requirement_utterances_by_meeting failed: %s", exc
            )
            return []

