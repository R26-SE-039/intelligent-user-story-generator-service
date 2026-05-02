# Transcription to User Stories — RAG Pipeline

A production-ready Python system that converts meeting transcripts into evidence-grounded
user stories with acceptance criteria using Retrieval-Augmented Generation (RAG).

Every generated story is linked back to source transcript chunks — no evidence, no story.

---

## Table of Contents

- [Features](#features)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Running the CLI Pipeline](#running-the-cli-pipeline)
- [Output Schema](#output-schema)
- [Prompt Templates](#prompt-templates)
- [Running Tests](#running-tests)
- [Offline / No API Key Mode](#offline--no-api-key-mode)
- [Architecture](#architecture)
- [Known Limitations](#known-limitations)

---

## Features

- Transcript JSON ingestion with speaker diarization and timestamp support
- Text normalization and semantic chunking with configurable overlap
- ChromaDB vector indexing with persistent local storage
- OpenAI embeddings (`text-embedding-3-small`) with SHA-256 hash fallback for offline use
- Evidence-grounded story generation via OpenAI chat models with structured JSON output
- Five modular prompt templates covering extraction, generation, critic, clarification, and guardrails
- Automatic story validation: format, evidence grounding, acceptance criteria quality
- FastAPI REST API with five endpoints
- CLI pipeline script for batch processing
- Full pytest test suite passing without an API key

---

## Project Structure

```
transcription-to-user-stories/
├── .env.example                        # Environment variable template
├── pyproject.toml                      # Project metadata and dependencies
├── requirements.txt                    # Flat dependency list
│
├── data/
│   ├── raw/
│   │   └── sample_transcript.json      # Sample transcript for testing
│   ├── processed/                      # Validated output landing zone
│   └── vector_index/
│       └── chroma/                     # ChromaDB persistent storage (auto-created)
│
├── docs/
│   └── architecture.md                 # Full architecture diagrams (Mermaid)
│
├── scripts/
│   ├── run_pipeline.py                 # CLI: full pipeline from transcript file
│   └── seed_sample_data.py             # CLI: index sample data into Chroma
│
├── src/
│   ├── app/
│   │   └── main.py                     # FastAPI entrypoint and route handlers
│   │
│   ├── core/
│   │   └── config.py                   # Pydantic Settings loaded from .env
│   │
│   ├── generation/
│   │   ├── story_generator.py          # Story generation service (LLM + fallback)
│   │   └── prompts/
│   │       ├── system_guardrail_prompt.txt
│   │       ├── story_generation_prompt.txt
│   │       ├── requirement_extraction_prompt.txt
│   │       ├── critic_dedup_prompt.txt
│   │       ├── clarification_questions_prompt.txt
│   │       └── user_story_prompt.txt
│   │
│   ├── ingestion/
│   │   ├── transcript_loader.py        # Load and validate Transcript from JSON
│   │   └── preprocess.py               # Normalize, chunk, propagate metadata
│   │
│   ├── models/
│   │   └── schemas.py                  # All Pydantic domain and API schemas
│   │
│   ├── pipeline/
│   │   └── orchestrator.py             # RAGPipeline: wires all components
│   │
│   ├── retrieval/
│   │   ├── chroma_store.py             # ChromaDB upsert and query
│   │   └── retriever.py                # Retriever facade
│   │
│   └── validation/
│       └── story_validator.py          # Story quality and format checks
│
└── tests/
    └── test_pipeline.py                # End-to-end and unit tests
```

---

## How It Works

The pipeline runs in five sequential steps:

```
Transcript JSON
      │
      ▼
┌─────────────┐
│  Ingestion  │  Normalize text, remove filler words, preserve timestamps
└──────┬──────┘
       │  List[Utterance]
       ▼
┌─────────────┐
│   Chunker   │  Split into overlapping word-count windows with metadata
└──────┬──────┘
       │  List[Chunk]
       ▼
┌─────────────┐
│ Chroma Index│  Embed each chunk → upsert into ChromaDB collection
└──────┬──────┘
       │  Query
       ▼
┌─────────────┐
│  Retrieval  │  top-k vector search with optional metadata filters
└──────┬──────┘
       │  evidence chunks
       ▼
┌─────────────┐
│ Generation  │  LLM generates stories grounded in evidence (JSON output)
└──────┬──────┘
       │  StoryBatch
       ▼
┌─────────────┐
│ Validation  │  Format, evidence refs, acceptance criteria quality checks
└──────┬──────┘
       │
       ▼
 List[GeneratedStory] + List[StoryIssue]
```

---

## Quick Start

### 1. Clone and set up environment

```bash
git clone <repo-url>
cd "transcription to user stories"

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
# Core + tests
pip install -e .[dev]

# Or from flat requirements file
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set `LLM_API_KEY` if you want real OpenAI generation and embeddings.
The system runs in offline fallback mode without any API key.

### 4. Seed sample data

```bash
python scripts/seed_sample_data.py
```

### 5. Run the full pipeline from CLI

```bash
python scripts/run_pipeline.py \
  --transcript data/raw/sample_transcript.json \
  --query "Create user stories for transcript automation"
```

### 6. Start the text-to-user-stories microservice

```bash
uvicorn services.text_to_user_stories.main:app --reload --port 8000
```

Text service docs available at: `http://localhost:8000/docs`

### 7. Start the speech-to-text microservice

```bash
uvicorn services.speech_to_text.main:app --reload --port 8001
```

Speech service docs available at: `http://localhost:8001/docs`

---

## Configuration

All settings are loaded from `.env` via `pydantic-settings`. Every field has a safe default for local use.

| Variable | Default | Description |
|---|---|---|
| `LLM_API_KEY` | _(none)_ | OpenAI API key; enables LLM generation + real embeddings |
| `CHAT_MODEL` | `gpt-4o-mini` | OpenAI chat model used for story generation |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model for chunk indexing |
| `CHROMA_PERSIST_DIRECTORY` | `data/vector_index/chroma` | Local path for ChromaDB persistence |
| `VECTOR_DB_COLLECTION` | `transcript_chunks` | ChromaDB collection name |
| `CHUNK_SIZE_WORDS` | `220` | Target word count per transcript chunk |
| `CHUNK_OVERLAP_WORDS` | `40` | Word overlap between consecutive chunks |
| `RETRIEVAL_TOP_K` | `8` | Number of evidence chunks retrieved per query |
| `APP_ENV` | `dev` | Application environment (`dev` / `prod`) |

---

## API Reference

Text service base URL: `http://localhost:8000`

Speech service base URL: `http://localhost:8001`

Interactive docs:
- `http://localhost:8000/docs` (text-to-user-stories)
- `http://localhost:8001/docs` (speech-to-text)

---

### `GET /health`

Check API availability.

**Response**
```json
{ "status": "ok" }
```

---

### `POST /ingest-transcript`

Preprocess and chunk a transcript without indexing it into Chroma.
Use this to inspect chunking behavior before committing to the index.

**Request body** — `Transcript`
```json
{
  "transcript_id": "meeting-001",
  "source": "product-discovery-call",
  "participants": ["Alice", "Bob"],
  "product_area": "transcription",
  "utterances": [
    {
      "speaker": "Alice",
      "text": "We need automated story generation from transcripts.",
      "timestamp_start": 0.0,
      "timestamp_end": 10.0
    }
  ]
}
```

**Response** — `IngestResponse`
```json
{
  "transcript_id": "meeting-001",
  "chunk_count": 2,
  "chunks": [ ... ]
}
```

---

### `POST /index-transcript`

Preprocess, embed, and index all chunks from a transcript into ChromaDB.

**Request body** — same `Transcript` format as above.

**Response**
```json
{
  "transcript_id": "meeting-001",
  "indexed_chunks": 3
}
```

---

### `POST /generate-stories`

Retrieve evidence chunks matching a query and generate user stories.
Transcripts must be indexed first via `/index-transcript`.

**Request body**
```json
{
  "query": "User story for automated transcript processing",
  "top_k": 5,
  "filters": { "product_area": "transcription" }
}
```

**Response** — `GenerateStoriesResponse`
```json
{
  "query": "...",
  "stories": [ ... ],
  "issues": [ ... ],
  "evidence_chunk_ids": ["meeting-001-chunk-0", "meeting-001-chunk-1"]
}
```

---

### `POST /pipeline/run`

Run the full pipeline in a single call: index → retrieve → generate → validate.

**Request body** — `PipelineRunRequest`
```json
{
  "transcript": { ... },
  "query": "User story for automated transcript processing",
  "top_k": 5,
  "filters": null
}
```

**Response** — `PipelineRunResponse`
```json
{
  "transcript_id": "meeting-001",
  "indexed_chunks": 3,
  "query": "...",
  "stories": [ ... ],
  "issues": [ ... ],
  "evidence_chunk_ids": [ ... ]
}
```

---

## Running the CLI Pipeline

```bash
python scripts/run_pipeline.py \
  --transcript data/raw/sample_transcript.json \
  --query "Generate user stories" \
  --top-k 5
```

Output is printed as JSON to stdout.

To index only:

```bash
python scripts/seed_sample_data.py
```

---

## Output Schema

Each generated story has the following structure:

```json
{
  "story_id": "US-001",
  "title": "Story title",
  "story": "As a product manager, I want ..., so that ...",
  "acceptance_criteria": [
    "Given ... When ... Then ...",
    "Given ... When ... Then ..."
  ],
  "priority": "Must | Should | Could",
  "confidence": 0.85,
  "status": "ready | needs_clarification",
  "clarification_questions": [],
  "evidence_refs": ["meeting-001-chunk-0", "meeting-001-chunk-2"]
}
```

Validation issues (if any) appear in the `issues` array alongside the stories:

```json
{
  "story_id": "US-001",
  "severity": "high | medium | low",
  "issue_type": "invalid_format | unsupported_claim | missing_acceptance_criteria | weak_acceptance_criterion",
  "detail": "Human-readable explanation"
}
```

---

## Prompt Templates

Located in `src/generation/prompts/`. All prompts enforce evidence-grounded, JSON-only output.

| File | Purpose |
|---|---|
| `system_guardrail_prompt.txt` | System-level instructions: evidence grounding, no markdown, JSON only |
| `story_generation_prompt.txt` | Main story generation with full output schema |
| `requirement_extraction_prompt.txt` | Extract structured requirements from evidence chunks |
| `critic_dedup_prompt.txt` | Detect quality issues and suggest story merges |
| `clarification_questions_prompt.txt` | Generate stakeholder questions for unclear stories |
| `user_story_prompt.txt` | Concise per-story conversion instructions |

---

## Running Tests

```bash
pytest
```

The test suite covers:

| Test | What it verifies |
|---|---|
| `test_chunking_behavior` | Chunker produces overlapping chunks with correct IDs |
| `test_retrieval_returns_metadata` | Chroma round-trip: upsert and query return correct metadata |
| `test_generation_output_matches_schema` | Story output matches `GeneratedStory` schema |
| `test_pipeline_happy_path` | Full pipeline: index → retrieve → generate succeeds end-to-end |

All tests run without an OpenAI API key using the built-in fallback mode.

---

## Offline / No API Key Mode

When `LLM_API_KEY` is not set:

- **Embeddings**: SHA-256 hash vectors (256 dimensions, deterministic)
- **Generation**: Deterministic story stub with evidence refs from retrieved chunks

This allows running the full pipeline locally for development, testing, and CI without any
external API dependency or cost.

To enable full LLM-powered generation, set `LLM_API_KEY` in your `.env` file.

---

## Architecture

See [docs/architecture.md](docs/architecture.md) for:

- Full system flowchart with all components
- End-to-end sequence diagram
- Data schema class diagram
- Component responsibility table
- Deployment topology
- Configuration reference
- Known limitations and recommended next steps

---

## Known Limitations

| Area | Current State | Recommended Next Step |
|---|---|---|
| Embeddings | Hash fallback not semantic | Add `sentence-transformers` for local semantic embeddings |
| Retrieval | Dense vector only | Add BM25 hybrid retrieval for keyword precision |
| Reranking | Not implemented | Add cross-encoder reranker between retrieval and generation |
| Generation | Single LLM pass | Add critic + auto-fix pass for quality improvement |
| Storage | Local Chroma only | Add managed vector DB (pgvector, Pinecone) for scale |
| Observability | Basic logging | Add OpenTelemetry tracing per pipeline run |
| Auth | None | Add API key or OAuth2 for production endpoints |
| Deduplication | Manual review only | Implement auto-merge of overlapping stories |
