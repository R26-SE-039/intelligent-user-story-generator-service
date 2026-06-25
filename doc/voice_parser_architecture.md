# Intelligent User Story Generator (RAG) Architecture

The **Intelligent User Story Generator Service** (formerly Voice Parser) is a real-time speech-to-text engine and AI-driven user story generation backend built with Python and FastAPI. It serves as the auditory and analytical core of the NextGenQA platform, converting live meeting audio into structured transcripts, and utilizing a Retrieval-Augmented Generation (RAG) pipeline to extract requirements, resolve conflicts, and generate detailed user stories.

## 🚀 Key Responsibilities
- **Real-Time Transcription**: Integrates with Azure Cognitive Services to provide low-latency live captions.
- **Meeting Management**: Handles the creation and joining of meeting rooms with secure in-memory passcodes.
- **WebSocket Orchestration**: Manages persistent connections for audio streaming, chat, and live updates.
- **RAG Pipeline**: Retrieves relevant context from transcripts and uses AI to generate structured user stories and acceptance criteria.
- **Stateless Authentication**: Verifies users independently using a shared `AUTH_SECRET` and JWTs issued by the Auth Service.

---

## 🌟 Service Features

### 1. Real-Time Collaborative Transcription
- **Live Captions**: Streams text segments immediately as they are recognized by Azure.
- **Partial Results**: Displays "typing" text in real-time before sentences are finalized.
- **Speaker Diarization**: Automatically labels text with the speaker's name and role.

### 2. Intelligent Meeting Management
- **Instant Rooms**: Create and join meetings with unique UUIDs and secure short passcodes (stored in-memory).
- **Participant Tracking**: Live broadcast of who is currently active in the meeting.
- **History Sync**: New participants automatically receive previous chat history upon joining.

### 3. Integrated Communication & Persistence
- **Meeting Chat**: In-meeting text messaging that is persisted alongside the transcript to the database.
- **Auto-Finalization**: Automatically consolidates real-time captions into a structured final transcript in PostgreSQL when the **last participant leaves** the meeting.

### 4. Advanced AI Analysis (RAG Pipeline)
- **Vector Embeddings**: Extracts requirements and stores them with `pgvector` embeddings.
- **User Story Generation**: Uses contextual retrieval to draft "Must/Should/Could" priority user stories.
- **Acceptance Criteria**: Automatically generates arrays of acceptance criteria attached to the stories.
- **Conflict Detection**: Flags conflicting requirements across different parts of the transcript.

---

## 🛠️ Technology Stack
- **Runtime**: Python 3.10+
- **Framework**: FastAPI (Asynchronous Web Framework)
- **Transcription**: Azure Cognitive Services (Speech SDK)
- **Real-Time**: WebSockets (Standard & Binary)
- **Database**: PostgreSQL (with `pgvector` extension)
- **Vector Search**: ChromaDB / pgvector
- **AI/LLM**: OpenRouter / LLaMA (or OpenAI)

---

## 📊 Database Schema (Normalized Domain Model)

The service recently migrated from a flat schema to a fully normalized PostgreSQL domain model.

### 1. `meetings` Table
Manages the lifecycle of meeting rooms.
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `UUID` (PK) | Unique meeting identifier |
| `title` | `text` | Display name of the meeting |
| `host_id` | `UUID` | ID of the user who created it |
| `status` | `text` | `active` or `stopped` |

### 2. `chat_messages` Table
Persistent storage for in-meeting chat messages.
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `UUID` (PK) | Unique message ID |
| `meeting_id` | `UUID` | References `meetings.id` |
| `sender_id` | `UUID` | References the user who sent it |
| `message` | `text` | Message content |

### 3. `transcripts` & `transcript_utterances`
Stores final, post-processed transcription payloads. `transcript_utterances` contains individual lines with `speaker_id` and `confidence_score`.

### 4. `requirements` & `requirement_embeddings`
Stores atomic requirements extracted from the meetings, alongside vector embeddings (via `pgvector`) for contextual retrieval.

### 5. `user_stories` & `acceptance_criteria`
Stores the generated user stories. Acceptance criteria are broken out into individual rows linked via `user_story_id`.

### 6. `conflicts`
Tracks contradictions or conflicting requirements raised during the meeting.

---

## 🛡️ Security & Authentication
This service implements the **Shared Secret Pattern**:
- It does **not** call the Auth Service to verify tokens over the network.
- It reads the `AUTH_SECRET` from its own `.env`.
- Using this secret, it decodes the `Authorization: Bearer <token>` header to extract the `user_id` and `role`.

---

## 📁 Project Structure
- **`src/pipeline/orchestrator.py`**: The RAG pipeline orchestrator managing ingestion, retrieval, and generation.
- **`src/speech/routes.py`**: Contains meeting logic and the complex WebSocket loop handling audio streams and Azure callbacks.
- **`src/speech/azure_client.py`**: Encapsulates Azure Speech SDK configuration and stream creation.
- **`postgres_gateway.py` & `persistence.py`**: Handles all CRUD operations using `psycopg2` directly against the PostgreSQL database.
- **`src/speech/session_store.py`**: A thread-safe in-memory store to track passcodes, active WebSocket connections, and real-time captions.
- **`src/core/config.py`**: Manages environment variables using Pydantic Settings.

---

## 🛠️ Local Development
1. Navigate to `/intelligent-user-story-generator-rag`.
2. Start the database: `cd agile-meeting-db-setup && docker-compose up -d --build`.
3. Configure `.env` with DB credentials, Azure keys, and LLM API keys.
4. Start the service: `python main.py` (runs on `localhost:8001`).
5. WebSocket URL: `ws://localhost:8001/ws/{meeting_id}`.
