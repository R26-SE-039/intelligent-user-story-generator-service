# RAG Service Documentation

This service provides an Intelligent User Story Generator using **Retrieval-Augmented Generation (RAG)**. It processes meeting transcripts, indexes them into ChromaDB, and uses OpenAI to extract requirements and generate validated user stories.

## Postman Collection
The file `postman_collection.json` in this directory can be imported into Postman for API testing.

### Setup
1. **Import**: Open Postman -> Import -> Select `postman_collection.json`.
2. **Variables**:
   - `base_url`: Defaults to `http://localhost:8002`.
   - `meeting_id`: The ID of the meeting you want to process.

### API Endpoints
- **GET /health**: Verify service status.
- **POST /index-transcript**: Ingests, chunks, and indexes a transcript into the vector database.
- **POST /generate-stories**: Performs retrieval and generates user stories based on a prompt/query.
- **POST /pipeline/run**: Executes the full end-to-end flow (Ingestion -> Indexing -> Retrieval -> Generation -> Validation).

## Technology Stack
- **FastAPI**: High-performance API framework.
- **ChromaDB**: Local vector database for semantic search.
- **OpenAI (GPT-4o)**: For requirement extraction and story writing.
- **Supabase**: For persistent storage of generated stories and metadata.
