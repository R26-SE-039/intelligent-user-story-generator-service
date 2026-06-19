-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table: speech_sessions
CREATE TABLE speech_sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    provider VARCHAR(100),
    status VARCHAR(50),
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Table: speech_captions
CREATE TABLE speech_captions (
    caption_id VARCHAR(255) PRIMARY KEY,
    session_id VARCHAR(255),
    speaker VARCHAR(255),
    text TEXT,
    created_at TIMESTAMP
);

-- Table: meetings
CREATE TABLE meetings (
    meeting_id VARCHAR(255) PRIMARY KEY,
    project_id VARCHAR(255),
    host_id VARCHAR(255),
    title VARCHAR(255),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    audio_file_url TEXT,
    meeting_status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: meeting_chat_messages
CREATE TABLE meeting_chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id VARCHAR(255),
    sender VARCHAR(255),
    text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: transcripts
CREATE TABLE transcripts (
    transcript_id VARCHAR(255) PRIMARY KEY,
    project_id VARCHAR(255),
    source VARCHAR(255),
    participants JSONB,
    metadata JSONB,
    updated_at TIMESTAMP
);

-- Table: transcript_utterances
CREATE TABLE transcript_utterances (
    utterance_id VARCHAR(255) PRIMARY KEY,
    transcript_id VARCHAR(255),
    utterance_index INTEGER,
    speaker VARCHAR(255),
    text TEXT,
    timestamp_start NUMERIC,
    timestamp_end NUMERIC,
    metadata JSONB
);

-- Table: transcript_chunks
CREATE TABLE transcript_chunks (
    chunk_id VARCHAR(255) PRIMARY KEY,
    transcript_id VARCHAR(255),
    chunk_index INTEGER,
    text TEXT,
    speakers JSONB,
    timestamp_start NUMERIC,
    timestamp_end NUMERIC,
    metadata JSONB
);

-- Table: story_runs
CREATE TABLE story_runs (
    story_run_id VARCHAR(255) PRIMARY KEY,
    transcript_id VARCHAR(255),
    project_id VARCHAR(255),
    query TEXT,
    issues JSONB,
    evidence_chunk_ids JSONB,
    created_at TIMESTAMP
);

-- Table: user_stories (generated_stories)
CREATE TABLE user_stories (
    generated_story_id VARCHAR(255) PRIMARY KEY,
    story_run_id VARCHAR(255),
    transcript_id VARCHAR(255),
    story_id VARCHAR(255),
    title VARCHAR(255),
    story TEXT,
    acceptance_criteria TEXT,
    priority VARCHAR(50),
    confidence NUMERIC,
    status VARCHAR(50),
    clarification_questions JSONB,
    evidence_refs JSONB
);

-- -----------------------------------------------------------------------------
-- Indexes
-- -----------------------------------------------------------------------------
CREATE INDEX idx_meetings_project_id ON meetings(project_id);
CREATE INDEX idx_meeting_chat_messages_meeting_id ON meeting_chat_messages(meeting_id);
CREATE INDEX idx_transcripts_project_id ON transcripts(project_id);
CREATE INDEX idx_transcript_utterances_transcript_id ON transcript_utterances(transcript_id);
CREATE INDEX idx_transcript_chunks_transcript_id ON transcript_chunks(transcript_id);
CREATE INDEX idx_story_runs_transcript_id ON story_runs(transcript_id);
CREATE INDEX idx_user_stories_story_run_id ON user_stories(story_run_id);
CREATE INDEX idx_speech_captions_session_id ON speech_captions(session_id);
