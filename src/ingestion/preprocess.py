"""Clean, normalize, and chunk transcripts."""

from __future__ import annotations

import re

from src.models.schemas import Chunk, Transcript, Utterance

_FILLER_PATTERN = re.compile(r"\b(um+|uh+|you know|like)\b", flags=re.IGNORECASE)
_SPACE_PATTERN = re.compile(r"\s+")


def normalize_text(text: str) -> str:
	"""Normalize text while preserving semantic content."""
	cleaned = _FILLER_PATTERN.sub(" ", text)
	cleaned = _SPACE_PATTERN.sub(" ", cleaned).strip()
	return cleaned


def preprocess_utterances(utterances: list[Utterance]) -> list[Utterance]:
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
	transcript: Transcript,
	chunk_size_words: int,
	chunk_overlap_words: int,
) -> list[Chunk]:
	"""Chunk transcript by utterance groups and carry metadata through each chunk."""
	utterances = preprocess_utterances(transcript.utterances)
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


def parse_raw_text(text: str, transcript_id: str) -> Transcript:
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
