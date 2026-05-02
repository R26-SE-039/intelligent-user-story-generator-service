"""Load transcript data from files or external systems."""

from __future__ import annotations

import json
from pathlib import Path

from ..models.schemas import Transcript


def load_transcript_from_file(path: str | Path) -> Transcript:
	"""Load and validate a transcript JSON file."""
	file_path = Path(path)
	data = json.loads(file_path.read_text(encoding="utf-8"))
	return Transcript.model_validate(data)


def save_json(path: str | Path, payload: dict) -> None:
	"""Save JSON payload to disk with stable formatting."""
	file_path = Path(path)
	file_path.parent.mkdir(parents=True, exist_ok=True)
	file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
