-- One email may now hold one account per company (plus one with no
-- company), instead of one account per tenant: the same person can be a
-- user at several client companies, each signing in from its own Odoo.
-- Before this, the second company's Odoo SSO failed with "This email is
-- already associated with a different account".
--
-- COALESCE puts every company-less account in one shared bucket, since
-- NULLs would otherwise never collide in a unique index.
--
-- Applied automatically on startup; safe to run again.

ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_tenant_id_email_key;
DROP INDEX IF EXISTS public.users_tenant_email_lower_uniq;

CREATE UNIQUE INDEX IF NOT EXISTS users_tenant_company_email_lower_uniq
    ON public.users (tenant_id, COALESCE(company_id::text, ''), LOWER(email));
