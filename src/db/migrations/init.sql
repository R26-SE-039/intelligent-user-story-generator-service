-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Table: MEETINGS
CREATE TABLE meetings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID,
    project_id UUID,
    host_id UUID,
    title VARCHAR(255),
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    status VARCHAR(50),
    audio_url TEXT
);

-- Table: CHAT_MESSAGES
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID REFERENCES meetings(id) ON DELETE CASCADE,
    sender_id UUID,
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: MEETING_PARTICIPANTS
CREATE TABLE meeting_participants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID REFERENCES meetings(id) ON DELETE CASCADE,
    user_id UUID,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(meeting_id, user_id)
);

-- Table: TRANSCRIPTS
CREATE TABLE transcripts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID REFERENCES meetings(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: TRANSCRIPT_UTTERANCES
CREATE TABLE transcript_utterances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transcript_id UUID REFERENCES transcripts(id) ON DELETE CASCADE,
    speaker_id UUID,
    speaker_name TEXT,
    start_time NUMERIC,
    end_time NUMERIC,
    utterance_text TEXT,
    confidence_score NUMERIC,
    utterance_type VARCHAR(100)
);

-- Table: REQUIREMENTS
CREATE TABLE requirements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID REFERENCES meetings(id) ON DELETE CASCADE,
    requirement_text TEXT,
    requirement_type VARCHAR(100),
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: REQUIREMENT_EMBEDDINGS
CREATE TABLE requirement_embeddings (
    requirement_id UUID PRIMARY KEY REFERENCES requirements(id) ON DELETE CASCADE,
    embedding vector(1536) -- Adjust dimensions if not 1536
);

-- Table: REQUIREMENT_UTTERANCE_MAPPING
CREATE TABLE requirement_utterance_mapping (
    requirement_id UUID REFERENCES requirements(id) ON DELETE CASCADE,
    utterance_id UUID REFERENCES transcript_utterances(id) ON DELETE CASCADE,
    PRIMARY KEY (requirement_id, utterance_id)
);

-- Table: CONFLICTS
CREATE TABLE conflicts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    requirement_a_id UUID REFERENCES requirements(id) ON DELETE CASCADE,
    requirement_b_id UUID REFERENCES requirements(id) ON DELETE CASCADE,
    conflict_type VARCHAR(100),
    severity VARCHAR(50),
    explanation TEXT
);

-- Table: USER_STORIES
CREATE TABLE user_stories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID REFERENCES meetings(id) ON DELETE CASCADE,
    title VARCHAR(255),
    story TEXT,
    priority VARCHAR(50),
    status VARCHAR(50)
);

-- Table: USER_STORY_REQUIREMENT_MAPPING
CREATE TABLE user_story_requirement_mapping (
    user_story_id UUID REFERENCES user_stories(id) ON DELETE CASCADE,
    requirement_id UUID REFERENCES requirements(id) ON DELETE CASCADE,
    PRIMARY KEY (user_story_id, requirement_id)
);

-- Table: ACCEPTANCE_CRITERIA
CREATE TABLE acceptance_criteria (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_story_id UUID REFERENCES user_stories(id) ON DELETE CASCADE,
    criteria TEXT
);

-- -----------------------------------------------------------------------------
-- Indexes
-- -----------------------------------------------------------------------------
CREATE INDEX idx_meetings_project_id ON meetings(project_id);
CREATE INDEX idx_chat_messages_meeting_id ON chat_messages(meeting_id);
CREATE INDEX idx_transcripts_meeting_id ON transcripts(meeting_id);
CREATE INDEX idx_meeting_participants_meeting_id ON meeting_participants(meeting_id);
CREATE INDEX idx_transcript_utterances_transcript_id ON transcript_utterances(transcript_id);
CREATE INDEX idx_requirements_meeting_id ON requirements(meeting_id);
CREATE INDEX idx_user_stories_meeting_id ON user_stories(meeting_id);
CREATE INDEX idx_acceptance_criteria_user_story_id ON acceptance_criteria(user_story_id);
