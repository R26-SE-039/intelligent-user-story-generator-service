"""Formatting and text normalization utilities."""

import re

_FILLER_PATTERN = re.compile(r"\b(um+|uh+|you know|like)\b", flags=re.IGNORECASE)
_SPACE_PATTERN = re.compile(r"\s+")

def normalize_text(text: str) -> str:
    """Normalize text while preserving semantic content."""
    cleaned = _FILLER_PATTERN.sub(" ", text)
    cleaned = _SPACE_PATTERN.sub(" ", cleaned).strip()
    return cleaned
