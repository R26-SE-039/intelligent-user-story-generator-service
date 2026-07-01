"""Repository for vector embeddings."""

from __future__ import annotations

from src.db.chroma import ChromaVectorStore
from src.models.transcript import Chunk


class EmbeddingRepository:
    def __init__(self, chroma: ChromaVectorStore) -> None:
        self._chroma = chroma

    def upsert(self, chunks: list[Chunk]) -> None:
        """Upsert chunk vectors with metadata into Chroma."""
        ids: list[str] = []
        documents: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, any]] = []

        for chunk in chunks:
            ids.append(chunk.chunk_id)
            documents.append(chunk.text)
            embeddings.append(self._chroma.embed(chunk.text))
            metadata: dict[str, any] = {
                "transcript_id": chunk.transcript_id,
                "chunk_index": chunk.chunk_index,
                "speakers": ",".join(chunk.speakers),
                "timestamp_start": chunk.timestamp_start if chunk.timestamp_start is not None else -1.0,
                "timestamp_end": chunk.timestamp_end if chunk.timestamp_end is not None else -1.0,
            }
            metadata.update(chunk.metadata)
            metadatas.append(metadata)

        self._chroma.collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)

    def query(self, query: str, top_k: int, filters: dict | None = None) -> list[Chunk]:
        """Query Chroma and convert results back into chunk objects."""
        results = self._chroma.collection.query(
            query_embeddings=[self._chroma.embed(query)],
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
