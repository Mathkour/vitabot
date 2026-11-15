-- Chooses the suggested questions on the /chat welcome screen:
--   is_featured  — starred by a tenant admin ("Show on home" in Knowledge
--                  Base); always shown first.
--   click_count  — times members clicked the question in chat; the most
--                  clicked fill any slots the admin's picks leave free.
--
-- Applied automatically on startup; safe to run again.

ALTER TABLE public.suggested_questions
    ADD COLUMN IF NOT EXISTS is_featured boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS click_count integer NOT NULL DEFAULT 0;
