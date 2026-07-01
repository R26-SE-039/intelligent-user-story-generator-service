# API Documentation

This directory contains the Postman collection for testing the **Intelligent Voice Parser Service**.

## Postman Collection
The file `postman_collection.json` can be imported directly into Postman.

### Setup
1. **Import**: Open Postman -> Import -> Select `postman_collection.json`.
2. **Variables**: The collection uses the following variables:
   - `base_url`: Defaults to `http://localhost:8001` (Voice Service).
   - `auth_token`: Your Auth Service JWT. You must set this in the collection variables or environment.
   - `meeting_id`: Used for meeting-specific requests.
   - `passcode`: Used for joining meetings.

### Key Features
- **Meeting Orchestration**: Create and join virtual rooms for collaboration.
- **Real-time Transcription**: Live voice-to-text via AssemblyAI WebSockets.
- **Persistent Chat**: Send and retrieve messages that stay linked to the meeting.
- **AI Analysis**: Generate summaries and action items from meeting data.

### Authentication
Every request (except health) requires an `Authorization: Bearer <token>` header. This token must be a valid JWT issued by the **Auth Service** (Port 8000).

### WebSocket Connection
Connect to `ws://localhost:8001/ws/{{meeting_id}}?name={{your_name}}` for real-time audio and chat streaming.

## Architecture

The project has been refactored into a modular **Clean Architecture** to ensure separation of concerns and maintainability.

- **`src/api/`**: Thin controllers (`routes/`), middlewares, and shared dependencies (like JWT validation).
- **`src/core/`**: Centralized configuration (`config.py`), logging, constants, and security utilities.
- **`src/db/`**: Low-level database connections and drivers (Postgres, ChromaDB), plus migration scripts (`migrations/`).
- **`src/models/`**: Pydantic domain models (e.g., transcripts, requirements, user stories, conflicts).
- **`src/repositories/`**: Data access abstraction. Services talk to repositories, never directly to the database.
- **`src/services/`**: Core business logic modules (speech transcription, vector retrieval, LLM story generation).
- **`src/prompts/`**: Central storage for all LLM prompts as `.txt` files.
- **`src/pipeline/`**: Orchestration components that string together ingestion, retrieval, generation, and validation.

## Database Schema

The service uses a normalized PostgreSQL database with `pgvector` for embeddings.

```mermaid
erDiagram
    MEETINGS ||--o{ CHAT_MESSAGES : contains
    MEETINGS ||--o{ TRANSCRIPTS : contains
    MEETINGS ||--o{ REQUIREMENTS : produces
    MEETINGS ||--o{ USER_STORIES : generates

    TRANSCRIPTS ||--o{ TRANSCRIPT_UTTERANCES : contains

    REQUIREMENTS ||--o{ REQUIREMENT_EMBEDDINGS : has

    REQUIREMENTS ||--o{ REQUIREMENT_UTTERANCE_MAPPING : traced_from
    TRANSCRIPT_UTTERANCES ||--o{ REQUIREMENT_UTTERANCE_MAPPING : source

    REQUIREMENTS ||--o{ CONFLICTS : involved_in

    REQUIREMENTS ||--o{ USER_STORY_REQUIREMENT_MAPPING : contributes_to
    USER_STORIES ||--o{ USER_STORY_REQUIREMENT_MAPPING : derived_from

    USER_STORIES ||--o{ ACCEPTANCE_CRITERIA : contains

    MEETINGS {
        uuid id PK
        uuid organization_id
        uuid project_id
        uuid host_id
        string title
        datetime start_time
        datetime end_time
        string status
        string audio_url
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
        float start_time
        float end_time
        string utterance_text
        float confidence_score
    }

    REQUIREMENTS {
        uuid id PK
        uuid meeting_id FK
        string requirement_text
        string requirement_type
        string status
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
        string conflict_type
        string severity
        string explanation
    }

    USER_STORIES {
        uuid id PK
        uuid meeting_id FK
        string title
        string story
        string priority
        string status
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

## Getting Started

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- An `.env` file — copy from `.env.example` and fill in your API keys

### 1. Configure Environment Variables
```bash
cp .env.example .env
```
Edit `.env` and fill in:
- `LLM_API_KEY` — OpenRouter or OpenAI key
- `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` — Azure Speech credentials
- `AUTH_SECRET` — must match the value in your **Auth Service**

The database connection is pre-configured for Docker:
```
DATABASE_URL=postgresql://meeting:nextgen_db@localhost:5434/meeting_db
DB_HOST=localhost
DB_PORT=5434
DB_USER=meeting
DB_PASSWORD=nextgen_db
DB_NAME=meeting_db
```

### 2. Start the PostgreSQL Database (Docker)
The project ships a `docker-compose.yml` in the root directory. The database uses the `pgvector/pgvector:pg16` image so `pgvector` is available out of the box. The schema in `src/db/migrations/init.sql` is applied automatically on first start.

```bash
# Start only the database (recommended during local development)
docker-compose up -d db
```

| Container | Image | Host Port | DB |
|---|---|---|---|
| `meeting_db` | `pgvector/pgvector:pg16` | `5434` | `meeting_db` |

> **Note**: Port `5434` is used to avoid conflicts with the Auth Service which runs on `5433`.

### 3. Run the Application (Local Dev)
```bash
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

### 4. Run Everything with Docker (Production)
To spin up **both** the database and the application together:
```bash
docker-compose up --build
```

The service will be available at `http://localhost:8001`.
Swagger UI: `http://localhost:8001/docs`

### 5. Stop the Containers
```bash
docker-compose down        # Stop containers, keep data volume
docker-compose down -v     # Stop containers AND delete DB data
```
