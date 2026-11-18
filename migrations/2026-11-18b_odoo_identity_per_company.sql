-- An Odoo SSO identity ("<client_key>:<odoo_user_id>") is now unique per
-- company rather than per tenant. Several customer Odoo databases can share
-- a Client Key, and Odoo numbers users from 1 in every database (the admin
-- is always user 2), so the same identity arriving from two companies is
-- two different people. Before this, the second company's sign-in reused
-- (and moved) the first company's account.
--
-- Applied automatically on startup; safe to run again.

-- Constraint first: an index backing a constraint can't be dropped directly.
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_tenant_odoo_identity_uniq;
DROP INDEX IF EXISTS public.users_tenant_odoo_identity_uniq;

CREATE UNIQUE INDEX IF NOT EXISTS users_tenant_odoo_identity_company_uniq
    ON public.users (tenant_id, odoo_identity, COALESCE(company_id::text, ''));
