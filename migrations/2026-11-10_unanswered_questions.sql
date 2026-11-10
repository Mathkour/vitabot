-- Unanswered Questions report.
--
-- Run once against the cpbot2 database, as the same superuser the restore
-- scripts use (the backfill below must see every tenant's rows, which
-- FORCE ROW LEVEL SECURITY hides from a normal user):
--
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f migrations/2026-11-10_unanswered_questions.sql
--
-- Safe to run again: the table, policy and backfill all skip what already
-- exists. The backend keeps working without this table (it just doesn't
-- record unanswered questions until it exists).

CREATE TABLE IF NOT EXISTS public.unanswered_questions (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    user_id uuid REFERENCES public.users(id) ON DELETE SET NULL,
    conversation_id uuid REFERENCES public.conversations(id) ON DELETE SET NULL,
    message_id uuid REFERENCES public.messages(id) ON DELETE SET NULL,
    category_id uuid REFERENCES public.categories(id) ON DELETE SET NULL,
    question text NOT NULL,
    status text DEFAULT 'open' NOT NULL
        CONSTRAINT unanswered_questions_status_check CHECK (status IN ('open', 'answered', 'dismissed')),
    answer text,
    answered_by uuid REFERENCES public.users(id) ON DELETE SET NULL,
    answered_at timestamp with time zone,
    -- The knowledge-base chunk the admin's answer was saved as, so the bot
    -- finds it next time. Deleting the chunk (or its document) only
    -- detaches it here.
    chunk_id uuid REFERENCES public.chunks(id) ON DELETE SET NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS unanswered_questions_tenant_status_idx
    ON public.unanswered_questions (tenant_id, status, created_at DESC);

-- Same tenant isolation as every other tenant table.
ALTER TABLE public.unanswered_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ONLY public.unanswered_questions FORCE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'unanswered_questions' AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON public.unanswered_questions
            USING (tenant_id = public.current_tenant_id())
            WITH CHECK (tenant_id = public.current_tenant_id());
    END IF;
END $$;

-- Backfill past "don't know" answers from the AI log. Each logged
-- no_info_response is matched to the chat message that asked it (same
-- tenant, same text, within 5 minutes before the log row) to recover the
-- user and conversation. Only chat questions are kept: a no_info_response
-- with no matching chat message came from the Document Index "Ask AI" page,
-- which searches its own page index, so an answer here wouldn't help it.
-- request_summary is cut at 300 characters, so the match compares the
-- first 300 characters.
INSERT INTO public.unanswered_questions (tenant_id, user_id, conversation_id, message_id, question, created_at)
SELECT a.tenant_id, c.user_id, c.id, m.id, m.content, a.created_at
FROM public.ai_predictions_log a
JOIN public.tenants t ON t.id = a.tenant_id
JOIN LATERAL (
    SELECT mm.id, mm.content, mm.conversation_id
    FROM public.messages mm
    WHERE mm.tenant_id = a.tenant_id
      AND mm.role = 'user'
      AND left(mm.content, 300) = a.request_summary
      AND mm.created_at BETWEEN a.created_at - interval '5 minutes' AND a.created_at
    ORDER BY mm.created_at DESC
    LIMIT 1
) m ON true
LEFT JOIN public.conversations c ON c.id = m.conversation_id
WHERE a.endpoint = 'no_info_response'
  AND a.request_summary IS NOT NULL
  AND btrim(a.request_summary) <> ''
  AND NOT EXISTS (
      SELECT 1 FROM public.unanswered_questions u
      WHERE u.tenant_id = a.tenant_id AND u.created_at = a.created_at
        AND left(u.question, 300) = a.request_summary
  );
