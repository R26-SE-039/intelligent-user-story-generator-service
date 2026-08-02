"""Requirement Extractor Service.

Integrates a fine-tuned ModernBERT classifier as a fast pre-filter before
calling the LLM. Only utterances classified as 'Requirement' by the
ModernBERT model proceed to the LLM for structured extraction.
"""

import json
import logging
import traceback
from uuid import uuid4
from pathlib import Path

from src.core.config import Settings
from src.core.llm import get_llm_client
from src.models.requirement import Requirement
from src.db.chroma import ChromaVectorStore
from src.services.requirement.utterance_classifier import UtteranceClassifier
from src.services.requirement.context_builder import ContextBuilder

LOGGER = logging.getLogger(__name__)

class RequirementExtractorService:
    def __init__(self):
        self.settings = Settings()
        
        # Note on OpenRouter: The 'openai' Python library is the official recommended 
        # client for OpenRouter. By passing `base_url=self.settings.llm_api_base` 
        # (which is set to https://openrouter.ai/api/v1), all requests are routed 
        # securely to OpenRouter, NOT OpenAI. 
        self.client = get_llm_client(self.settings)
        self.model = self.settings.chat_model
        
        # We reuse the existing ChromaVectorStore which already has built-in logic 
        # to handle embeddings gracefully (including local hashing fallbacks if 
        # the provider doesn't support the OpenAI embeddings endpoint).
        self.vector_store = ChromaVectorStore(self.settings)
        
        # Define prompts directory
        self.prompts_dir = Path(__file__).resolve().parent.parent.parent / "prompts"

        # Fine-tuned ModernBERT classifier — loaded once as a singleton
        self.classifier = UtteranceClassifier()
        self.context_builder = ContextBuilder()

    def _load_prompt(self, name: str) -> str:
        return (self.prompts_dir / name).read_text(encoding="utf-8")

    def get_embedding(self, text: str) -> list[float]:
        """Generate a 3072-dimensional vector embedding for the text using Gemini embedding model."""
        if not text:
            return [0.0] * 3072

        try:
            emb = self.vector_store.embed(text)

            # pgvector requires exactly 3072 dimensions as defined in migration.
            if len(emb) < 3072:
                emb = emb + [0.0] * (3072 - len(emb))
            elif len(emb) > 3072:
                emb = emb[:3072]

            return emb
        except Exception as e:
            LOGGER.warning(f"[RequirementExtractor] Failed to generate embedding: {e}")
            return [0.0] * 3072

    def extract(
        self,
        utterance_text: str,
        meeting_id: str,
        previous_utterance: str = "",
        next_utterance: str = "",
    ) -> tuple[list[Requirement], str]:
        """Extract requirements from a single utterance text.

        Args:
            utterance_text: The current meeting utterance to classify and extract from.
            meeting_id: The meeting identifier to tag requirements with.
            previous_utterance: The utterance spoken just before this one (for context).
            next_utterance: The utterance spoken just after this one (for context).

        Returns:
            Tuple of (list of Requirement objects, classification_label).
        """
        if not utterance_text or len(utterance_text.split()) < 3:
            return [], "None"

        # --- Phase 1: ModernBERT Pre-filter ---
        # Build the contextual input string the model was trained on
        context_text = self.context_builder.build_single(
            current=utterance_text,
            previous=previous_utterance,
            next_utterance=next_utterance,
        )
        classification = self.classifier.classify(context_text)

        LOGGER.info(
            "[ModernBERT Classification] Utterance: '%s...' -> Label: %s (Confidence: %.1f%%)",
            utterance_text[:80].replace("\n", " "),
            classification.label,
            classification.confidence * 100,
        )

        # Fast-path: skip LLM call for purely irrelevant utterances (e.g. Question, Discussion, Chitchat)
        # Note: In software engineering meetings, requirements are frequently phrased as Suggestions
        should_extract = classification.is_requirement or classification.label in ("Requirement", "Suggestion")
        if not should_extract:
            LOGGER.info(
                "[ModernBERT Classification] Skipping LLM extraction - Label '%s' is not a Requirement/Suggestion.",
                classification.label,
            )
            return [], classification.label

        LOGGER.info(
            "[ModernBERT Classification] ModernBERT confirmed '%s'. Proceeding to LLM extraction...",
            classification.label,
        )
            
        system_prompt = self._load_prompt("requirement_extraction_prompt.txt")
        
        try:
            input_text = f"System Instructions:\n{system_prompt}\n\nUser Input:\n{utterance_text}"
            interaction = self.client.interactions.create(
                model=self.model,
                input=input_text,
                response_format={
                    "type": "text",
                    "mime_type": "application/json"
                }
            )
            
            content = interaction.output_text.strip()
            print(f"[RequirementExtractor] LLM Response: {content}")
            
            # Clean up potential markdown formatting
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
                
            content = content.strip()
            
            if not content or content == "[]":
                return [], classification.label
                
            items = json.loads(content)
            requirements = []
            
            for item in items:
                if "text" in item and "type" in item:
                    requirements.append(
                        Requirement(
                            requirement_id=str(uuid4()),
                            meeting_id=meeting_id,
                            requirement_text=item["text"],
                            requirement_type=item["type"],
                            status="active"
                        )
                    )
            return requirements, classification.label
            
        except Exception as e:
            print(f"[RequirementExtractor] Error extracting requirements: {e}")
            traceback.print_exc()
            return [], classification.label
