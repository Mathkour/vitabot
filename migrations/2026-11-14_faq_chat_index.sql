-- Lets chat answer from FAQ items and error solutions (services/faq_index.py).
--
-- Each entry points at the knowledge-base chunk it's indexed as. Deleting the
-- chunk only detaches it; the backend's startup backfill re-indexes any entry
-- whose chunk_id is NULL (including every existing entry after this runs).
--
-- Applied automatically on startup; safe to run again.

ALTER TABLE public.faq_items
    ADD COLUMN IF NOT EXISTS chunk_id uuid REFERENCES public.chunks(id) ON DELETE SET NULL;

ALTER TABLE public.error_solutions
    ADD COLUMN IF NOT EXISTS chunk_id uuid REFERENCES public.chunks(id) ON DELETE SET NULL;
