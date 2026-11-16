-- The /chat welcome screen now also draws its cards from the FAQ (see
-- GET /suggested-questions/featured), so FAQ items need the same usage
-- counter suggested_questions got in 2026-11-15_featured_suggested_questions.
--
-- Applied automatically on startup; safe to run again.

ALTER TABLE public.faq_items
    ADD COLUMN IF NOT EXISTS click_count integer NOT NULL DEFAULT 0;
