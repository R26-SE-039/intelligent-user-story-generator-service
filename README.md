# Intelligent User Story Generator Service

This service parses transcripts from collaborative agile meetings, extracts requirements, manages BA conflict resolution, and generates validated agile user stories using advanced LLM reasoning and retrieval-augmented generation (RAG).

## Architecture & Tech Stack
- **Framework**: FastAPI (Python)
- **Database**: Neon Cloud PostgreSQL (with `pgvector` for embedding storage)
- **Vector Search**: pgvector & ChromaDB (for transcript retrieval)
- **Transcription**: Azure Cognitive Services Speech SDK (Real-time WebSockets & batch parsing)
- **Security**: JWT-based Authentication (integrated with Auth Service)

The project follows clean architecture principles:
- `src/api/` — API Routes (speech and pipeline) & middlewares.
- `src/core/` — Settings configuration and logging.
- `src/db/` — Database gateway (PostgreSQL, ChromaDB) and init files.
- `src/models/` — Domain data models (Pydantic).
- `src/repositories/` — Repository abstractions for persistent data.
- `src/services/` — Internal services (Speech client, RAG utilities, User Story validation engine).
- `src/prompts/` — Grounded prompt templates.
- `src/pipeline/` — Pipeline execution models.

---

## Getting Started

### Prerequisites
- Python 3.10+
- Neon Cloud PostgreSQL instance
- API Keys: Azure Speech Key, LLM API Key (OpenRouter/Gemini), and Auth JWT Secret

### 1. Setup Environment
Copy the example environment file and fill in your keys:
```bash
cp .env.example .env
```
Ensure you set your Neon PostgreSQL credentials:
```ini
# PostgreSQL (Neon Cloud)
DATABASE_URL=postgresql://neondb_owner:<password>@<neon-host>/meeting_db?sslmode=require&channel_binding=require
DB_HOST=<neon-host>
DB_PORT=5432
DB_USER=neondb_owner
DB_PASSWORD=<password>
DB_NAME=meeting_db
DB_SSLMODE=require
```

### 2. Apply Database Schema
Since Neon is a cloud database, apply the SQL schema to initialize the tables:
- **Neon Dashboard**: Go to the SQL Editor in your Neon console, paste the contents of `src/db/initialize/init.sql`, and click **Run**.
- **CLI (optional)**:
  ```bash
  psql "postgresql://neondb_owner:<password>@<neon-host>/meeting_db?sslmode=require" -f src/db/initialize/init.sql
  ```

### 3. Run the Service (Local Development)
Install dependencies and run Uvicorn:
```bash
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```
The API docs will be available at `http://localhost:8001/docs`.

### 4. Run using Docker Compose
The `docker-compose.yml` runs only the application container. The database connects directly to your Neon instance.
```bash
docker-compose up --build
```

---

## Database Schema

```mermaid
erDiagram
    MEETINGS ||--o{ CHAT_MESSAGES : contains
    MEETINGS ||--o{ TRANSCRIPTS : contains
    MEETINGS ||--o{ REQUIREMENTS : produces
    MEETINGS ||--o{ USER_STORIES : generates
    MEETINGS ||--o{ MEETING_PARTICIPANTS : contains

    TRANSCRIPTS ||--o{ TRANSCRIPT_UTTERANCES : contains
    TRANSCRIPT_UTTERANCES ||--o{ UTTERANCE_EMBEDDINGS : has

    REQUIREMENT_THREADS ||--o{ REQUIREMENTS : groups
    REQUIREMENTS ||--o{ REQUIREMENT_EMBEDDINGS : has
    REQUIREMENTS ||--o{ REQUIREMENT_UTTERANCE_MAPPING : traced_from
    TRANSCRIPT_UTTERANCES ||--o{ REQUIREMENT_UTTERANCE_MAPPING : source

    REQUIREMENTS ||--o{ CONFLICTS : involved_in

    REQUIREMENTS ||--o{ USER_STORY_REQUIREMENT_MAPPING : contributes_to
    USER_STORIES ||--o{ USER_STORY_REQUIREMENT_MAPPING : derived_from
    USER_STORIES ||--o{ ACCEPTANCE_CRITERIA : contains
    USER_STORIES ||--o{ USER_STORY_VALIDATIONS : validates

    MEETINGS {
        uuid id PK
        uuid organization_id
        uuid project_id
        uuid iteration_id
        uuid host_id
        string title
        datetime start_time
        datetime end_time
        string status
        string audio_url
    }

    MEETING_PARTICIPANTS {
        uuid id PK
        uuid meeting_id FK
        uuid user_id
        datetime joined_at
    }

    CHAT_MESSAGES {
        uuid id PK
        uuid meeting_id FK
        uuid sender_id
        string message
        datetime created_at
    }

    TRANSCRIPTS {
        uuid id PK
        uuid meeting_id FK
        datetime created_at
    }

    TRANSCRIPT_UTTERANCES {
        uuid id PK
        uuid transcript_id FK
        uuid speaker_id
        string speaker_name
        float start_time
        float end_time
        string utterance_text
        float confidence_score
        string utterance_type
    }

    UTTERANCE_EMBEDDINGS {
        uuid utterance_id PK, FK
        vector embedding
    }

    REQUIREMENT_THREADS {
        uuid id PK
        uuid meeting_id FK
        string requirement_title
        string summary
        string state
        vector embedding
        datetime created_at
        datetime updated_at
    }

    REQUIREMENTS {
        uuid id PK
        uuid meeting_id FK
        uuid thread_id FK
        string requirement_text
        string requirement_type
        string status
        uuid duplicate_of_id FK
        datetime created_at
    }

    REQUIREMENT_EMBEDDINGS {
        uuid requirement_id PK, FK
        vector embedding
    }

    REQUIREMENT_UTTERANCE_MAPPING {
        uuid requirement_id PK, FK
        uuid utterance_id PK, FK
    }

    CONFLICTS {
        uuid id PK
        uuid requirement_a_id FK
        uuid requirement_b_id FK
        uuid source_meeting_id FK
        string conflict_type
        string severity
        string explanation
        string status
        string suggested_resolution
        string previous_text_a
        string previous_text_b
        uuid resolved_by
        datetime resolved_at
    }

    USER_STORIES {
        uuid id PK
        uuid meeting_id FK
        string title
        string story
        string priority
        string status
    }

    USER_STORY_VALIDATIONS {
        uuid id PK
        uuid user_story_id FK
        string status
        numeric overall_quality_score
        text recommendation
        numeric semantic_similarity
        numeric evidence_score
        numeric invest_score
        numeric hallucination_score
        numeric rule_score
        jsonb invest_breakdown
        jsonb issues
        datetime validated_at
    }

    USER_STORY_REQUIREMENT_MAPPING {
        uuid user_story_id PK, FK
        uuid requirement_id PK, FK
    }

    ACCEPTANCE_CRITERIA {
        uuid id PK
        uuid user_story_id FK
        string criteria
    }
```

---

## API Routes Documentation

### 1. Speech & Meeting Orchestration (`/api/v1/speech`)
- `POST /meeting/create` — Create an instant meeting. Resolves current project iteration context via Auth Service.
- `POST /meeting/join` — Join a room using `meeting_id` and passcode.
- `GET /meeting/{meeting_id}/chats` — Retrieve text messages exchanged in the room.
- `GET /meeting/{meeting_id}/transcript` — Retrieve transcript captions (either memory-buffered or Postgres fallback).
- `POST /meeting/{meeting_id}/finalize` — Finalize raw transcription, execute sentence tokenization, mapping, vector indexing, and close room.
- `GET /meeting/{meeting_id}/requirements` — Retrieve extracted requirement threads and items.
- `GET /meeting/{meeting_id}/conflicts` — Retrieve requirements conflicts.
- `POST /meeting/{meeting_id}/conflicts/{conflict_id}/resolve` — Resolve a specific requirement conflict.
- `GET /project/{project_id}/conflicts` — Retrieve all requirement conflicts across meetings for a project.
- `GET /project/{project_id}/iteration/stories` — Fetch all user stories linked to the active iteration of a project.
- `WS /ws/{meeting_id}` — WebSocket voice & transcription endpoint.

### 2. User Story Generation (`/api/v1/pipeline`)
- `POST /run` — Generate stories directly from a given transcript request body.
- `POST /upload` — Upload a `.txt` transcript file, generate a virtual meeting linked to the current active iteration, and ingest.
- `POST /generate-from-requirements` — Ingest active requirement details and output agile stories.
- `POST /user-stories/{story_id}/update` — Update manual changes to a story and trigger 5-layer backend re-validation.
- `POST /user-stories/{story_id}/status` — BA manual override endpoint to mark a story as Approved, Rejected, or Reset.
