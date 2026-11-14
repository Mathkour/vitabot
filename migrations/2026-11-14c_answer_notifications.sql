-- Tells the person who asked an unanswered question that an admin has now
-- answered it (topbar bell). user_seen_at is when they last saw the answer;
-- an answer saved after it (or never seen) is a notification.
--
-- Existing answers are marked seen, so this doesn't flood users with
-- notifications for questions answered before the feature existed.
--
-- Applied automatically on startup; safe to run again.

ALTER TABLE public.unanswered_questions
    ADD COLUMN IF NOT EXISTS user_seen_at timestamp with time zone;

DO $$
DECLARE
    t record;
BEGIN
    FOR t IN SELECT id FROM public.tenants LOOP
        PERFORM set_config('app.current_tenant', t.id::text, true);
        UPDATE public.unanswered_questions
        SET user_seen_at = now()
        WHERE tenant_id = t.id AND status = 'answered' AND user_seen_at IS NULL;
    END LOOP;
END $$;
