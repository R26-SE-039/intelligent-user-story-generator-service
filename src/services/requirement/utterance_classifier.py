"""ModernBERT Utterance Classifier.

Wraps the fine-tuned ModernBERT model for local, fast utterance classification.
The model classifies meeting utterances into 9 categories:
    Requirement, Decision, Action Item, Suggestion, Risk,
    Clarification, Question, Rejected, Future Feature

The model is loaded once (singleton) when the class is first instantiated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

from src.core.config import Settings

LOGGER = logging.getLogger(__name__)

# Absolute path to the default model directory relative to service root
_DEFAULT_MODEL_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "models"
    / "modernbert-utterance-classifier"
)

# Labels that should proceed to requirement extraction
REQUIREMENT_LABELS = {"Requirement"}


@dataclass
class ClassificationResult:
    """Result of utterance classification."""
    label: str
    confidence: float
    is_requirement: bool


class UtteranceClassifier:
    """Singleton-pattern ModernBERT classifier for utterance classification."""

    _instance: "UtteranceClassifier | None" = None
    _lock: Lock = Lock()

    def __new__(cls) -> "UtteranceClassifier":
        with cls._lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._initialized = False
                cls._instance = instance
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._load_model()

    def _load_model(self) -> None:
        """Load the fine-tuned ModernBERT model and tokenizer from disk."""
        service_root = Path(__file__).resolve().parent.parent.parent.parent
        configured_path = Path(Settings().modernbert_model_path)

        if configured_path.is_absolute():
            model_dir = configured_path
        else:
            model_dir = (service_root / configured_path).resolve()

        if not model_dir.exists():
            fallback_dir = (service_root.parent / "ModernBERT Traning" / "model_output" / "checkpoint-1350").resolve()
            if fallback_dir.exists():
                model_dir = fallback_dir

        model_path = str(model_dir)
        LOGGER.info("[UtteranceClassifier] Loading model from: %s", model_path)

        if not model_dir.exists():
            raise FileNotFoundError(
                f"ModernBERT model directory not found at: {model_path}\n"
                "Please ensure 'models/modernbert-utterance-classifier/' or 'ModernBERT Traning/model_output/checkpoint-1350' exists "
                "with config.json, model.safetensors, tokenizer.json files."
            )

        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)

        # Use GPU if available, otherwise CPU
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self.model.to(self.device)
        self.model.eval()  # Set to inference mode

        LOGGER.info(
            "[UtteranceClassifier] Model loaded successfully on device: %s",
            self.device,
        )

    def classify(self, text: str) -> ClassificationResult:
        """Classify a single utterance context string.

        Args:
            text: Formatted context string from ContextBuilder, e.g.:
                  "Previous: X | Utterance: Y | Next: Z"

        Returns:
            ClassificationResult with label, confidence, and is_requirement flag.
        """
        if not text or not text.strip():
            return ClassificationResult(
                label="Question", confidence=0.0, is_requirement=False
            )

        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=256,
            padding=True,
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            probabilities = torch.softmax(logits, dim=-1)
            predicted_id = torch.argmax(probabilities, dim=-1).item()
            confidence = probabilities[0][predicted_id].item()

        label = self.model.config.id2label[predicted_id]
        conf_pct = round(confidence * 100, 2)
        is_req = label in REQUIREMENT_LABELS

        LOGGER.info(
            "[ModernBERT Classification] Input: '%s...' -> Label: %s (Confidence: %.1f%%, IsRequirement: %s)",
            text[:70].replace("\n", " "),
            label,
            conf_pct,
            is_req
        )

        return ClassificationResult(
            label=label,
            confidence=round(confidence, 4),
            is_requirement=is_req,
        )

    def classify_batch(self, texts: list[str]) -> list[ClassificationResult]:
        """Classify a batch of utterance context strings efficiently.

        Args:
            texts: List of formatted context strings from ContextBuilder.

        Returns:
            List of ClassificationResult objects in the same order as input.
        """
        if not texts:
            return []

        inputs = self.tokenizer(
            texts,
            return_tensors="pt",
            truncation=True,
            max_length=256,
            padding=True,
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            probabilities = torch.softmax(logits, dim=-1)
            predicted_ids = torch.argmax(probabilities, dim=-1).tolist()

        results = []
        for i, pred_id in enumerate(predicted_ids):
            label = self.model.config.id2label[pred_id]
            confidence = probabilities[i][pred_id].item()
            is_req = label in REQUIREMENT_LABELS
            LOGGER.info(
                "[ModernBERT Classification Batch] Item %d/%d: '%s...' -> Label: %s (Confidence: %.1f%%, IsRequirement: %s)",
                i + 1,
                len(texts),
                texts[i][:60].replace("\n", " "),
                label,
                round(confidence * 100, 1),
                is_req
            )
            results.append(
                ClassificationResult(
                    label=label,
                    confidence=round(confidence, 4),
                    is_requirement=is_req,
                )
            )

        return results
