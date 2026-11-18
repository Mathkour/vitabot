-- Extra Odoo host slugs that sign into a company, for customers whose Odoo
-- subdomain doesn't match the company's slug (the slug is fixed once the
-- company exists). Odoo SSO checks these before slugs, so an alias also
-- wins over a company auto-created from that host before it was added.
--
-- almisk.vitacareonline.com belongs to company "misk".
--
-- Applied automatically on startup; safe to run again.

ALTER TABLE public.companies
    ADD COLUMN IF NOT EXISTS sso_aliases text[] NOT NULL DEFAULT '{}';

DO $$
DECLARE
    t record;
BEGIN
    FOR t IN SELECT id FROM public.tenants LOOP
        PERFORM set_config('app.current_tenant', t.id::text, true);
        UPDATE public.companies
        SET sso_aliases = array_append(sso_aliases, 'almisk')
        WHERE tenant_id = t.id AND slug = 'misk' AND NOT ('almisk' = ANY(sso_aliases));
    END LOOP;
END $$;
