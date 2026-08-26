# Intelligent User Story Generation Service
## Complete End-to-End Architecture & Data Flow Specification

---

## 1. High-Level System Architecture Overview

```mermaid
flowchart TB
    subgraph Client["1. Client Layer"]
        MIC["🎙️ Microphone Input\n(Browser Web Audio API)"]
        WORKLET["⚡ AudioWorkletProcessor\n(Downsample to 16kHz Int16 PCM)"]
        FE_DASH["🖥️ NextGenQA Frontend Dashboard\n(React / TypeScript / Tailwind)"]
        MIC --> WORKLET
        WORKLET -->|"WebSocket Binary Chunks (1280B / 40ms)"| WS_EP["/ws/speech/meeting/{meeting_id}"]
    end

    subgraph AudioEngine["2. Real-Time Audio & Speech-to-Text Pipeline"]
        WS_EP --> COORD["LiveMeetingCoordinator"]
        COORD -->|"PushAudioInputStream (16kHz Mono)"| AZ_STREAM["AzureStreamService"]
        AZ_STREAM -->|"Azure Speech SDK C-API"| AZ_CLOUD["☁️ Azure Cognitive Services (Speech-to-Text)"]
        AZ_CLOUD -->|"handle_partial_result"| AZ_PARTIAL["Partial Captions Stream"]
        AZ_CLOUD -->|"handle_final_result"| AZ_FINAL["Final Recognized Utterance"]
        AZ_PARTIAL -->|"WebSocket Broadcast"| FE_DASH
        AZ_FINAL -->|"WebSocket Broadcast & Save"| TRANS_REPO[("Transcript Repository")]
    end

    subgraph Classification["3. Context-Aware Utterance Classification"]
        AZ_FINAL --> CTX_BUILDER["ContextBuilder\n('Previous: X | Utterance: Y | Next: Z')"]
        CTX_BUILDER --> MBERT["ModernBERT Utterance Classifier\n(Fine-Tuned 9 Classes)"]
        MBERT --> FILTER{"Classification Filter\nIs Requirement or Suggestion?"}
        FILTER -->|"No (Question, Clarification, Chitchat)"| CAP_ONLY["Store Caption / Update UI Only"]
        FILTER -->|"Yes (Requirement / Suggestion)"| EXTRACT_TRIGGER["Trigger LLM Extraction"]
    end

    subgraph ReqProcessing["4. Requirement Extraction & Embedding Pipeline"]
        EXTRACT_TRIGGER --> LLM_EXTRACT["Gemini 2.0 Flash / LLM\n(Requirement Extraction Prompt)"]
        LLM_EXTRACT -->|"Structured JSON Array"| REQ_PARSER["Requirement Object Builder (UUID)"]
        REQ_PARSER --> EMB_GEN["Gemini Embedding Model\n(models/gemini-embedding-001)"]
        EMB_GEN -->|"3072-Dimensional Vector"| PG_REQ[("PostgreSQL\n(requirements & requirement_embeddings)")]
    end

    subgraph ThreadManager["5. Requirement Thread Lifecycle & State Machine"]
        REQ_PARSER --> THREAD_SRV["RequirementThreadService"]
        THREAD_SRV -->|"pgvector Cosine Distance <= 0.30"| THREAD_SEARCH{"Similar Thread\nExists?"}
        THREAD_SEARCH -->|"Yes (Match Found)"| THREAD_TRANS["Evaluate State Transition (LLM / Rule Heuristic)\nDISCOVERED ➔ DISCUSSION ➔ REFINED ➔ VALIDATED"]
        THREAD_SEARCH -->|"No (New Topic)"| THREAD_NEW["Create New Thread\n(State: DISCOVERED)"]
        THREAD_TRANS --> PG_THREADS[("PostgreSQL\n(requirement_threads)")]
        THREAD_NEW --> PG_THREADS
        PG_THREADS -->|"WebSocket Signal 'THREAD_UPDATED'"| FE_DASH
    end

    subgraph ConflictEngine["6. Sliding Window Conflict & Duplicate Detection"]
        REQ_PARSER --> CAND_RETRIEVE["Vector Search / Sliding Window\nTop-10 Candidates (Meeting / Project Scope)"]
        CAND_RETRIEVE --> LLM_CONFLICT["Gemini LLM Conflict Detector\n(conflict_detection_prompt.txt)"]
        LLM_CONFLICT --> CONF_CHECK{"Conflict Evaluation"}
        CONF_CHECK -->|"Duplicate First Rule"| DUP_HANDLER["Mark status='duplicate'\nSet duplicate_of_id"]
        CONF_CHECK -->|"Direct Logical Contradiction"| CONF_HANDLER["Mark status='conflicted'\nGenerate Suggested Resolution"]
        CONF_CHECK -->|"Complementary / No Contradiction"| CLEAN_HANDLER["Maintain status='active'"]
        DUP_HANDLER --> PG_CONFLICTS[("PostgreSQL\n(conflicts table)")]
        CONF_HANDLER --> PG_CONFLICTS
        PG_CONFLICTS -->|"WebSocket Broadcast 'conflicts'"| FE_DASH
    end

    subgraph StoryGeneration["7. Agile User Story Generation & 5-Layer Validation"]
        BA_ACTION["👤 Business Analyst Review & Finalize"] --> FIN_REQS["Finalized Active Requirements"]
        FIN_REQS --> RAG_RETRIEVER["pgvector Utterance Chunks Retriever (RAG)"]
        RAG_RETRIEVER --> STORY_GEN["StoryGenerator (Gemini LLM)\n(story_from_requirements_prompt.txt)"]
        STORY_GEN --> GEN_STORIES["Generated Stories Batch\n(As a... I want... So that...) +\nBDD Given-When-Then Acceptance Criteria"]
        
        GEN_STORIES --> V_L1["Layer 1: Rule-Based Validation (10%)\nRegex Structure, Fields, BDD AC Syntax, Duplicates"]
        GEN_STORIES --> V_L2["Layer 2: Evidence Grounding (40%)\nGemini Embeddings Cosine Similarity vs RAG Chunks"]
        GEN_STORIES --> V_L3["Layer 3: Hallucination Detection (5%)\nLLM Grounding & Unsupported Claims Check"]
        GEN_STORIES --> V_L4["Layer 4: INVEST Quality (20%)\nIndependent, Negotiable, Valuable, Estimable, Small, Testable"]
        
        V_L1 & V_L2 & V_L3 & V_L4 --> V_L5["Layer 5: Overall Quality Engine\nWeighted Formula\n>=80: Approved | >=50: Needs Review | <50: Rejected"]
        V_L5 --> PG_STORIES[("PostgreSQL\n(user_stories & validation_results)")]
        PG_STORIES --> JIRA_EXPORT["🚀 Jira REST API Export / Backlog Integration"]
    end
```

---

## 2. Detailed End-to-End Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Speaker as 🎙️ Speaker / Client Mic
    participant Worklet as ⚡ Frontend AudioWorklet
    participant WS as 🔌 WebSocket Server
    participant Coord as 🎛️ LiveMeetingCoordinator
    participant Azure as ☁️ Azure Speech SDK
    participant Classifier as 🧠 ModernBERT Classifier
    participant Extractor as 📝 Requirement Extractor (LLM)
    participant Embedder as 🔢 Gemini Embeddings
    participant DB as 🗄️ PostgreSQL (pgvector)
    participant ThreadMgr as 🧵 RequirementThreadService
    participant ConflictDet as ⚔️ ConflictDetectorService
    participant StoryGen as 📖 StoryGenerator & 5-Layer Validator

    %% Step 1: Audio Stream
    Speaker->>Worklet: Speaks: "Users must be able to reset their password via email OTP within 5 minutes."
    Worklet->>WS: Sends binary Int16 PCM chunks (16kHz mono, 1280 bytes)
    WS->>Coord: Streams chunk into audio buffer
    Coord->>Azure: Writes 1280B blocks to PushAudioInputStream
    Azure-->>Coord: SpeechRecognitionEventArgs (Final result recognized)
    Coord->>WS: Broadcasts transcription payload to meeting room

    %% Step 2: ModernBERT Classification
    Coord->>Classifier: classify("Previous: ... | Utterance: 'Users must be able to reset...' | Next: ...")
    Classifier-->>Coord: Result: { label: "Requirement", confidence: 0.9842, is_requirement: true }

    %% Step 3: LLM Extraction & Vectorization
    Coord->>Extractor: extract("Users must be able to reset their password via email OTP within 5 minutes.")
    Extractor-->>Coord: Returns Requirement object (id="req-7f8a9b1c", text="...", type="functional")
    Coord->>DB: INSERT into requirements (id, text, type, status='active')
    Coord->>Embedder: get_embedding(requirement_text)
    Embedder-->>Coord: Returns 3072-dim float vector
    Coord->>DB: INSERT into requirement_embeddings (pgvector)

    %% Step 4: Thread Grouping
    Coord->>ThreadMgr: process_requirement(meeting_id, req_id, text, embedding)
    ThreadMgr->>DB: SELECT * FROM requirement_threads WHERE (embedding <=> target) <= 0.30
    alt Existing Thread Found
        ThreadMgr->>ThreadMgr: Evaluate State Transition (DISCOVERED ➔ DISCUSSION ➔ REFINED ➔ VALIDATED)
        ThreadMgr->>DB: UPDATE requirement_threads SET state='REFINED', summary=...
    else No Thread Found
        ThreadMgr->>DB: INSERT into requirement_threads (state='DISCOVERED', ...)
    end
    ThreadMgr->>WS: Broadcast {"type": "THREAD_UPDATED"}

    %% Step 5: Conflict & Duplicate Detection
    Coord->>ConflictDet: detect(new_requirement, embedding)
    ConflictDet->>DB: SELECT Top-10 candidates via pgvector cosine similarity (<=>)
    DB-->>ConflictDet: Returns Top-10 prior requirements
    ConflictDet->>ConflictDet: verify_conflicts_with_llm(new_req, candidates)
    alt Duplicate Detected
        ConflictDet->>DB: UPDATE requirements SET status='duplicate', duplicate_of_id=req_b_id
    else Logical Conflict Detected
        ConflictDet->>DB: UPDATE requirements SET status='conflicted' (both reqs)
        ConflictDet->>DB: INSERT into conflicts (req_a_id, req_b_id, conflict_type, suggested_resolution)
        ConflictDet->>WS: Broadcast {"type": "conflicts", data: [...]}
    end

    %% Step 6 & 7: User Story Generation & Validation
    Speaker->>StoryGen: Trigger Story Generation for Finalized Meeting Requirements
    StoryGen->>DB: SELECT * FROM requirements WHERE meeting_id=X AND status='active'
    StoryGen->>DB: Retrieve RAG Utterance Chunks via pgvector cosine distance
    StoryGen->>StoryGen: Generate Agile User Stories & BDD ACs via LLM
    
    %% 5-Layer Validation
    StoryGen->>StoryGen: Layer 1: Rule-Based Validation (Regex, Syntax, Duplicates)
    StoryGen->>Embedder: Layer 2: Cosine Similarity between Story & RAG Chunks
    StoryGen->>StoryGen: Layer 3: Hallucination Detection (LLM Grounding)
    StoryGen->>StoryGen: Layer 4: INVEST Quality Scoring (LLM 0-5 scale)
    StoryGen->>StoryGen: Layer 5: Overall Quality Score Calculation & Status Decision (Approved / Needs Review / Rejected)
    StoryGen->>DB: INSERT into user_stories, acceptance_criteria, validation_results
    StoryGen-->>WS: Return complete generated stories & validation breakdown
```

---

## 3. Requirement Thread Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> DISCOVERED: Initial Requirement Spoken & Extracted
    
    DISCOVERED --> DISCUSSION: Further Discussion / Elaboration Occurs
    DISCUSSION --> REFINED: Specific Constraints, Timers, or Scope Added
    DISCUSSION --> DISCARDED: Stakeholders Reject / Drop Feature
    
    REFINED --> VALIDATED: Stakeholders Express Agreement ("confirm", "approved", "finalized")
    REFINED --> DISCARDED: Dropped During Sprint Planning
    
    VALIDATED --> REFINED: Scope Modification or New Detail Introduced
    VALIDATED --> [*]: Locked for User Story Generation
```

---

## 4. Conflict vs. Duplicate Decision Matrix

```mermaid
flowchart TD
    NEW_REQ["Incoming Requirement (Req A)"] --> RETRIEVE["Retrieve Top-10 Similar Prior Requirements (Req B)"]
    RETRIEVE --> PROMPT["Send to Conflict & Duplicate Detection LLM"]
    
    PROMPT --> DUP_CHECK{"Same Underlying Business Rule / Workflow?"}
    DUP_CHECK -->|"Yes (Identical intent / workflow)"| DUP_ACTION["Mark Req A Status as 'duplicate'\nSet duplicate_of_id = Req B\nConflict Type: 'duplicate'"]
    
    DUP_CHECK -->|"No"| CONTRADICT_CHECK{"Direct Logical Impossibility / Contradiction?"}
    
    CONTRADICT_CHECK -->|"Yes (e.g. 5-min expiry vs 15-min expiry)"| CONF_ACTION["Mark Both Reqs Status as 'conflicted'\nLog Conflict Record with Severity & Suggested Resolution"]
    
    CONTRADICT_CHECK -->|"No (Independent / Complementary features)"| CLEAN_ACTION["Mark Status as 'active'\nNo Conflict Logged"]
```

---

## 5. Step-by-Step Sample Data Payloads

### Step 1: Voice Streaming Ingestion Payload
```json
{
  "event": "azure_final_transcription",
  "data": {
    "text": "Users must be able to reset their password via email OTP within 5 minutes.",
    "speaker_id": "conn-9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "speaker_name": "Kasun (Lead BA)",
    "is_final": true,
    "timestamp_start": 12.4,
    "timestamp_end": 16.8
  }
}
```

### Step 2: ModernBERT Classification Output
```json
{
  "input_context": "Previous: We need a secure way for users who forget credentials. | Utterance: Users must be able to reset their password via email OTP within 5 minutes. | Next: Yes, that sounds good.",
  "label": "Requirement",
  "confidence": 0.9842,
  "is_requirement": true
}
```

### Step 3: Extracted Requirement & Vector Embedding
```json
{
  "requirement_id": "req-7f8a9b1c-1234-4567-89ab-cdef01234567",
  "meeting_id": "meet-c83b92d1-921a-4932-8411-ae932145bc89",
  "requirement_text": "The system shall send a 6-digit OTP to the user's registered email with a 5-minute expiration time for password reset.",
  "requirement_type": "functional",
  "status": "active",
  "embedding_sample": [0.0241, -0.0153, 0.0892, 0.0041, 0.0318]
}
```

### Step 4: Requirement Thread State Machine
```json
{
  "thread_id": "th-550e8400-e29b-41d4-a716-446655440000",
  "title": "Email OTP Password Reset",
  "summary": "Users receive a 6-digit OTP via email expiring in 5 minutes. Rate-limited to 3 attempts.",
  "state": "REFINED",
  "linked_requirements": ["req-7f8a9b1c-1234-4567-89ab-cdef01234567"]
}
```

### Step 5: Conflict & Duplicate Detection Result
```json
{
  "conflict_id": "conf-4a2b1c3d-9999-8888-7777-666655554444",
  "requirement_a_id": "req-7f8a9b1c-1234-4567-89ab-cdef01234567",
  "requirement_b_id": "req-999a888b-1111-2222-3333-444455556666",
  "conflict_type": "temporal",
  "severity": "high",
  "explanation": "Requirement A mandates a 5-minute OTP expiry window, whereas Requirement B mandates a 15-minute expiry window for password reset.",
  "suggested_resolution": "The system shall send a 6-digit OTP for password reset that expires after 10 minutes, balancing security and user convenience.",
  "status": "active"
}
```

### Step 6: Generated Agile User Story & BDD Acceptance Criteria
```json
{
  "story_id": "US-101",
  "title": "Password Reset via Email OTP",
  "story": "As a registered customer, I want to reset my password using a time-limited email OTP, so that I can securely regain access to my account if I forget my credentials.",
  "acceptance_criteria": [
    "Given a registered user is on the forgot password page, When they submit their valid registered email, Then a 6-digit OTP is sent to their email with a 5-minute expiration timestamp.",
    "Given the user received an OTP, When they enter the correct 6-digit OTP within 5 minutes, Then they are redirected to the set new password screen.",
    "Given an OTP was sent more than 5 minutes ago, When the user enters the expired OTP, Then an error message 'OTP has expired. Please request a new code.' is displayed.",
    "Given a user enters an incorrect OTP 3 consecutive times, When the 3rd attempt fails, Then the OTP session is locked for 15 minutes."
  ],
  "priority": "Must",
  "confidence": 0.95,
  "status": "ready",
  "evidence_refs": ["req-7f8a9b1c-1234-4567-89ab-cdef01234567"]
}
```

### Step 7: 5-Layer Validation Scores & Approval
```json
{
  "story_id": "US-101",
  "rule_score": 100.0,
  "semantic_similarity": 0.8924,
  "evidence_score": 89.24,
  "hallucination_score": 0.02,
  "invest_score": 4.75,
  "invest_breakdown": {
    "Independent": 0.95,
    "Negotiable": 0.90,
    "Valuable": 1.00,
    "Estimable": 0.95,
    "Small": 0.95,
    "Testable": 1.00,
    "overall": 0.95
  },
  "overall_quality_score": 90.12,
  "status": "Approved",
  "issues": [],
  "recommendation": "User story is validated and ready for the product backlog."
}
```

---

## 6. Mathematical Formula for 5-Layer Quality Score

$$\text{Overall Score} = (0.40 \times \text{Evidence}) + (0.25 \times \text{Semantic}) + (0.20 \times \text{INVEST}) + (0.10 \times \text{Rule}) + (0.05 \times (1 - \text{Hallucination}))$$

| Layer | Component | Weight | Target Metric |
| :--- | :--- | :---: | :--- |
| **Layer 1** | **Rule-Based Validation** | **10%** | Regex story structure, non-empty fields, BDD GWT syntax, no duplicate titles (0–100) |
| **Layer 2** | **Evidence Grounding** | **40%** | Max cosine similarity between Story embedding and RAG Transcript Chunks (0–100) |
| **Layer 3** | **Hallucination Detection** | **5%** | Gemini LLM claim grounding assessment ($0.0 = \text{clean}, 1.0 = \text{hallucinated}$) |
| **Layer 4** | **INVEST Quality Scoring** | **20%** | Independent, Negotiable, Valuable, Estimable, Small, Testable (Normalised to 0–100) |
| **Layer 5** | **Overall Decision Threshold** | **Final** | $\ge 80.0 \implies \mathbf{Approved}$<br>$\ge 50.0 \implies \mathbf{Needs\ Review}$<br>$< 50.0 \implies \mathbf{Rejected}$ |
