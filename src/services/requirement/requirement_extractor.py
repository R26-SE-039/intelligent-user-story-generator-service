"""Requirement Extractor Service."""

import json
import traceback
from uuid import uuid4
from pathlib import Path

from src.core.config import Settings
from src.core.llm import get_llm_client
from src.models.requirement import Requirement
from src.db.chroma import ChromaVectorStore

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

    def _load_prompt(self, name: str) -> str:
        return (self.prompts_dir / name).read_text(encoding="utf-8")

    def get_embedding(self, text: str) -> list[float]:
        """Generate a vector embedding for the text using the shared vector store logic."""
        if not text:
            return [0.0] * 1536
            
        try:
            # This calls ChromaVectorStore.embed() which automatically handles 
            # OpenRouter vs OpenAI differences or falls back to local hashing.
            emb = self.vector_store.embed(text)
            
            # pgvector requires exactly 1536 dimensions as defined in init.sql.
            # If the fallback hash generator returns 256, we must pad it to 1536.
            if len(emb) < 1536:
                emb = emb + [0.0] * (1536 - len(emb))
            elif len(emb) > 1536:
                emb = emb[:1536]
                
            return emb
        except Exception as e:
            print(f"[RequirementExtractor] Warning: Failed to generate embedding: {e}")
            return [0.0] * 1536

    def extract(self, utterance_text: str, meeting_id: str) -> list[Requirement]:
        """Extract requirements from a single utterance text."""
        if not utterance_text or len(utterance_text.split()) < 3:
            return []
            
        system_prompt = self._load_prompt("requirement_extraction_prompt.txt")
        
        try:
            # This API call looks like OpenAI, but because of the base_url we injected
            # in __init__, it goes directly to OpenRouter using your configured model!
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": utterance_text}
                ],
                temperature=0.1,
                max_tokens=300
            )
            
            content = response.choices[0].message.content.strip()
            print(f"[RequirementExtractor] LLM Response: {content}")
            
            # Clean up potential markdown formatting
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
                
            content = content.strip()
            
            if not content or content == "[]":
                return []
                
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
            return requirements
            
        except Exception as e:
            print(f"[RequirementExtractor] Error extracting requirements: {e}")
            traceback.print_exc()
            return []
