-- Migration: Create public.conversations and public.chat_messages tables with Row Level Security (RLS)
-- Timestamp: 20260809133000

CREATE TABLE IF NOT EXISTS public.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New Conversation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    citations JSONB NULL,
    retrieved_chunk_count INTEGER DEFAULT 0,
    retrieval_time_ms INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Add indexes on conversations.user_id and chat_messages.conversation_id
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON public.conversations (user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_id ON public.chat_messages (conversation_id);

-- Enable Row Level Security (RLS)
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

-- RLS Policies for conversations
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can view their own conversations') THEN
        CREATE POLICY "Users can view their own conversations"
        ON public.conversations FOR SELECT TO authenticated
        USING (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can insert their own conversations') THEN
        CREATE POLICY "Users can insert their own conversations"
        ON public.conversations FOR INSERT TO authenticated
        WITH CHECK (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can update their own conversations') THEN
        CREATE POLICY "Users can update their own conversations"
        ON public.conversations FOR UPDATE TO authenticated
        USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete their own conversations') THEN
        CREATE POLICY "Users can delete their own conversations"
        ON public.conversations FOR DELETE TO authenticated
        USING (auth.uid() = user_id);
    END IF;
END $$;

-- RLS Policies for chat_messages
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can view messages of their own conversations') THEN
        CREATE POLICY "Users can view messages of their own conversations"
        ON public.chat_messages FOR SELECT TO authenticated
        USING (
            conversation_id IN (
                SELECT id FROM public.conversations WHERE user_id = auth.uid()
            )
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can insert messages into their own conversations') THEN
        CREATE POLICY "Users can insert messages into their own conversations"
        ON public.chat_messages FOR INSERT TO authenticated
        WITH CHECK (
            conversation_id IN (
                SELECT id FROM public.conversations WHERE user_id = auth.uid()
            )
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete messages of their own conversations') THEN
        CREATE POLICY "Users can delete messages of their own conversations"
        ON public.chat_messages FOR DELETE TO authenticated
        USING (
            conversation_id IN (
                SELECT id FROM public.conversations WHERE user_id = auth.uid()
            )
        );
    END IF;
END $$;
