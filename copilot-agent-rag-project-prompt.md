# Copilot Agent Prompt: Build RAG Project (Transcription -> User Stories)

Use this exact prompt with Copilot Agent.

## Prompt to Copilot Agent

You are my implementation agent. Build a production-ready Python RAG project that converts meeting transcripts into user stories with acceptance criteria.

Goal
Create an end-to-end system:
1. Ingest transcript files
2. Chunk and embed transcript content
3. Store and retrieve vectors from ChromaDB
4. Generate user stories from retrieved evidence
5. Validate output with strict JSON schema
6. Provide API endpoints and runnable scripts

Tech Requirements
1. Python 3.11
2. FastAPI for API layer
3. ChromaDB as vector database
4. OpenAI embeddings and chat model (configurable via environment variables)
5. Pydantic for schemas and validation
6. Pytest for tests
7. Logging and error handling in all major modules

Project Structure to Create
1. src/app for FastAPI entrypoint and routes
2. src/ingestion for transcript loading and preprocessing
3. src/retrieval for embedding, index, retriever, reranker hooks
4. src/generation for prompt templates and story generation
5. src/pipeline for end-to-end orchestration
6. src/validation for output schema checks and quality checks
7. data/raw, data/processed, data/vector_index
8. tests for unit and integration tests
9. docs for architecture and runbook

Functional Requirements
1. Transcript input model with transcript_id, participants, utterances, timestamps
2. Preprocessing that cleans noise while preserving traceable evidence
3. Chunking with overlap and metadata propagation
4. Chroma index creation and upsert logic
5. Retrieval by query with top_k and metadata filtering
6. Story generation in strict JSON output:
   - story_id
   - title
   - story in As a / I want / so that format
   - acceptance_criteria list in Given/When/Then format
   - priority
   - confidence
   - status
   - clarification_questions
   - evidence_refs
7. Reject unsupported claims (no evidence, no story)
8. End-to-end pipeline command that runs ingest -> index -> retrieve -> generate -> validate

API Endpoints
1. POST /ingest-transcript
2. POST /index-transcript
3. POST /generate-stories
4. POST /pipeline/run
5. GET /health

Prompting Requirements
1. Create separate prompt templates for:
   - requirement extraction
   - story generation
   - story critic/dedup
   - clarification question generation
2. All prompts must enforce evidence-grounded output
3. All prompts must return schema-compliant JSON only

Config Requirements
1. Create .env.example with all required keys
2. Support configurable chunk_size, chunk_overlap, retrieval_top_k, model names
3. Add safe defaults for local development

Developer Experience
1. Add dependency file and install instructions
2. Add run instructions for API and pipeline script
3. Add sample transcript input file
4. Add seed script to index sample data
5. Add minimal but meaningful tests:
   - chunking behavior
   - retrieval returns metadata
   - generation output matches schema
   - pipeline happy path

Quality Bar
1. Clean architecture with separable components
2. Type hints everywhere
3. Docstrings for public functions
4. Structured logs on important operations
5. Avoid hardcoding model names and paths

Execution Instructions
1. First create files and code
2. Then run tests
3. Then fix any errors
4. Finally provide:
   - what was created
   - how to run
   - known limitations
   - next recommended improvements

Important Constraints
1. Do not leave placeholders for core logic
2. Implement real working code for ingestion, indexing, retrieval, generation orchestration, and validation
3. Keep code modular so Chroma can be replaced later
4. Keep prompts in dedicated prompt files
5. Use only ASCII characters in source files

If anything is unclear, make sensible defaults and continue implementation without asking unnecessary questions.

## Shorter version if you want fast generation

Build a complete Python 3.11 FastAPI RAG project for transcript-to-user-story generation using ChromaDB, OpenAI embeddings/chat, Pydantic schemas, and pytest. Implement ingestion, preprocessing, chunking with metadata, Chroma indexing, retrieval with top_k and filters, evidence-grounded story generation, strict JSON schema validation, and end-to-end pipeline orchestration. Add endpoints for ingest, index, generate, and full pipeline run. Include .env.example, sample data, prompt templates, tests, and docs. Run tests and fix issues before finalizing.
