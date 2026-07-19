-- Step 1: Clear existing embeddings and alter table to support 3072 dimensions
TRUNCATE TABLE requirement_embeddings;
ALTER TABLE requirement_embeddings ALTER COLUMN embedding TYPE vector(3072);

-- Step 2: Create REQUIREMENT_THREADS table
CREATE TABLE IF NOT EXISTS requirement_threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID REFERENCES meetings(id) ON DELETE CASCADE,
    requirement_title VARCHAR(255) NOT NULL,
    summary TEXT,
    state VARCHAR(50) DEFAULT 'DISCOVERED',
    embedding vector(3072),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Step 3: Link existing requirements table to threads
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='requirements' AND column_name='thread_id'
    ) THEN
        ALTER TABLE requirements ADD COLUMN thread_id UUID REFERENCES requirement_threads(id) ON DELETE SET NULL;
    END IF;
END $$;
