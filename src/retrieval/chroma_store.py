"""Chroma vector store integration with configurable embedding backend."""

from __future__ import annotations

import hashlib
from typing import Any

import chromadb
from openai import OpenAI

from ..core.config import Settings
from ..models.schemas import Chunk


def _hash_embedding(text: str, dim: int = 256) -> list[float]:
    """Create deterministic embedding for local tests and offline mode."""
    values: list[float] = []
    seed = text.encode("utf-8")
    while len(values) < dim:
        digest = hashlib.sha256(seed).digest()
        for byte in digest:
            values.append((byte / 255.0) * 2.0 - 1.0)
            if len(values) == dim:
                break
        seed = digest
    return values


class ChromaVectorStore:
    """Vector operations for transcript chunks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.chroma_persist_directory.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.settings.chroma_persist_directory))
        self.collection = self.client.get_or_create_collection(name=self.settings.vector_db_collection)
        # Only use OpenAI embeddings when using native OpenAI endpoint; OpenRouter does not support them
        _is_openai_native = "openai.com" in getattr(settings, "llm_api_base", "")
        self.openai_client = OpenAI(api_key=settings.llm_api_key) if (settings.llm_api_key and _is_openai_native) else None

    def _embed(self, text: str) -> list[float]:
        if self.openai_client is None:
            return _hash_embedding(text)
        response = self.openai_client.embeddings.create(
            model=self.settings.embedding_model,
            input=text,
        )
        return response.data[0].embedding

    def upsert(self, chunks: list[Chunk]) -> None:
        """Upsert chunk vectors with metadata into Chroma."""
        ids: list[str] = []
        documents: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []

        for chunk in chunks:
            ids.append(chunk.chunk_id)
            documents.append(chunk.text)
            embeddings.append(self._embed(chunk.text))
            metadata: dict[str, Any] = {
                "transcript_id": chunk.transcript_id,
                "chunk_index": chunk.chunk_index,
                "speakers": ",".join(chunk.speakers),
                "timestamp_start": chunk.timestamp_start if chunk.timestamp_start is not None else -1.0,
                "timestamp_end": chunk.timestamp_end if chunk.timestamp_end is not None else -1.0,
            }
            metadata.update(chunk.metadata)
            metadatas.append(metadata)

        self.collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)

    def query(self, query: str, top_k: int, filters: dict | None = None) -> list[Chunk]:
        """Query Chroma and convert results back into chunk objects."""
        results = self.collection.query(
            query_embeddings=[self._embed(query)],
            n_results=top_k,
            where=filters,
            include=["documents", "metadatas"],
        )

        docs = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        ids = results.get("ids", [[]])[0]

        chunks: list[Chunk] = []
        for idx, chunk_id in enumerate(ids):
            metadata = metadatas[idx] if idx < len(metadatas) else {}
            transcript_id = str(metadata.get("transcript_id", "unknown"))
            speakers_raw = str(metadata.get("speakers", ""))
            speakers = [item for item in speakers_raw.split(",") if item]
            timestamp_start = metadata.get("timestamp_start")
            timestamp_end = metadata.get("timestamp_end")
            parsed_start = None if timestamp_start in (-1.0, None) else float(timestamp_start)
            parsed_end = None if timestamp_end in (-1.0, None) else float(timestamp_end)

            clean_metadata = {
                key: value
                for key, value in metadata.items()
                if key
                not in {"transcript_id", "chunk_index", "speakers", "timestamp_start", "timestamp_end"}
            }

            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    transcript_id=transcript_id,
                    chunk_index=int(metadata.get("chunk_index", idx)),
                    text=docs[idx] if idx < len(docs) else "",
                    speakers=speakers,
                    timestamp_start=parsed_start,
                    timestamp_end=parsed_end,
                    metadata=clean_metadata,
                )
            )
        return chunks
