-- Migration: Create public.document_chunks table for persistent BM25 and metadata
-- Timestamp: 20260906160000

CREATE TABLE IF NOT EXISTS public.document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    chunk_id INTEGER NOT NULL,
    page INTEGER NULL,
    source_file TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT uq_document_chunks_doc_chunk UNIQUE (document_id, chunk_id)
);

-- Indexes for fast user chunk retrieval and document deletion
CREATE INDEX IF NOT EXISTS idx_document_chunks_user_id ON public.document_chunks (user_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON public.document_chunks (document_id);

-- Enable Row Level Security (RLS)
ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY;

-- RLS Policies for document_chunks
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can view their own document chunks') THEN
        CREATE POLICY "Users can view their own document chunks"
        ON public.document_chunks FOR SELECT TO authenticated
        USING (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can insert their own document chunks') THEN
        CREATE POLICY "Users can insert their own document chunks"
        ON public.document_chunks FOR INSERT TO authenticated
        WITH CHECK (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete their own document chunks') THEN
        CREATE POLICY "Users can delete their own document chunks"
        ON public.document_chunks FOR DELETE TO authenticated
        USING (auth.uid() = user_id);
    END IF;
END $$;
