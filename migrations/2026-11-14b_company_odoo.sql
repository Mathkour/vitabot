-- Per-company Ask Odoo, managed from the admin portal (Companies page).
--
-- ask_odoo_enabled: whether the company's users get Ask Odoo at all.
-- odoo_connection_id: the company's own Odoo (a row of odoo_client_connections,
--   so passwords stay encrypted the same way and Odoo SSO keeps working).
--
-- Backfill: a company whose users already reach an Odoo through SSO
-- (users.odoo_client_key) is linked to that connection and enabled, so
-- nothing that works today stops working. Runs per tenant inside the
-- tenant's RLS context, since companies/users FORCE ROW LEVEL SECURITY.
--
-- Applied automatically on startup; safe to run again.

ALTER TABLE public.companies
    ADD COLUMN IF NOT EXISTS ask_odoo_enabled boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS odoo_connection_id uuid
        REFERENCES public.odoo_client_connections(id) ON DELETE SET NULL;

DO $$
DECLARE
    t record;
BEGIN
    FOR t IN SELECT id FROM public.tenants LOOP
        PERFORM set_config('app.current_tenant', t.id::text, true);
        UPDATE public.companies c
        SET odoo_connection_id = pick.connection_id,
            ask_odoo_enabled = true
        FROM (
            -- The connection most of the company's SSO users use.
            SELECT DISTINCT ON (u.company_id) u.company_id, occ.id AS connection_id
            FROM public.users u
            JOIN public.odoo_client_connections occ ON occ.client_key = u.odoo_client_key
            WHERE u.company_id IS NOT NULL AND u.tenant_id = t.id
            GROUP BY u.company_id, occ.id
            ORDER BY u.company_id, count(*) DESC
        ) pick
        WHERE c.id = pick.company_id
          AND c.tenant_id = t.id
          AND c.odoo_connection_id IS NULL;
    END LOOP;
END $$;
