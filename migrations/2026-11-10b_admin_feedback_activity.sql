-- Answer Feedback review + Activity Log.
-- Applied automatically on backend startup (services/migrations.py).
-- Safe to run again.

-- Answer Feedback: an admin marks each thumbs-down as fixed (the correct
-- answer was taught to the bot) or dismissed (the answer was fine).
ALTER TABLE public.ratings ADD COLUMN IF NOT EXISTS review_status text;
ALTER TABLE public.ratings ADD COLUMN IF NOT EXISTS reviewed_by uuid REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE public.ratings ADD COLUMN IF NOT EXISTS reviewed_at timestamp with time zone;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ratings_review_status_check') THEN
        ALTER TABLE public.ratings ADD CONSTRAINT ratings_review_status_check
            CHECK (review_status IS NULL OR review_status IN ('fixed', 'dismissed'));
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ratings_tenant_score_idx ON public.ratings (tenant_id, score, created_at DESC);

-- Activity Log: who changed what in the admin area.
CREATE TABLE IF NOT EXISTS public.activity_log (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    user_id uuid REFERENCES public.users(id) ON DELETE SET NULL,
    action text NOT NULL,          -- e.g. 'document.upload', 'faq.update'
    summary text NOT NULL,         -- human-readable, e.g. the file or question
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE INDEX IF NOT EXISTS activity_log_tenant_created_idx ON public.activity_log (tenant_id, created_at DESC);

ALTER TABLE public.activity_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE ONLY public.activity_log FORCE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'activity_log' AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON public.activity_log
            USING (tenant_id = public.current_tenant_id())
            WITH CHECK (tenant_id = public.current_tenant_id());
    END IF;
END $$;
