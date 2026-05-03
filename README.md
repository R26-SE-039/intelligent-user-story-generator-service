# NextGenQA: Intelligent User Story Generator (RAG)

A general-purpose **Retrieval-Augmented Generation (RAG)** microservice that converts meeting transcripts from **any domain** into professional, evidence-grounded User Stories.

## 🚀 Getting Started

### 1. Environment Setup
Create a `.env` file from `.env.example` and add your **OpenAI API Key**:
```env
LLM_API_KEY=your_key_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_key_here
```

### 2. Run the Service
Start the FastAPI server on **Port 8002**:
```powershell
uvicorn main:app --host 0.0.0.0 --port 8002 --reload
```

## 🛠️ API Endpoints

- **`POST /pipeline/run`**: Full end-to-end processing (Transcript -> Vector Index -> AI Generation -> Supabase).
- **`POST /index-transcript`**: Processes and indexes a transcript from any project or domain.
- **`POST /generate-stories`**: Generates stories based on the current context in the vector database.
- **`GET /health`**: Service status check.

## 🧠 Domain-Agnostic RAG
Unlike simple AI prompts, this system ensures every User Story is backed by **actual transcript evidence**. It semantic-searches your meeting data to find the exact requirements discussed, regardless of whether the project is about Healthcare, Finance, E-commerce, or any other field.
