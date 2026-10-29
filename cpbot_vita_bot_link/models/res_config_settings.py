from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    vita_bot_client_key = fields.Char(
        string='Vita Bot Client Key',
        config_parameter='cpbot_vita_bot_link.client_key',
        help='Identifies this company to the Vita Care cpbot backend so Ask '
             'Odoo questions route to this company\'s own Odoo data instead '
             'of another client\'s. Provided by Vita Care when this company '
             'is set up as a client.',
    )

    # Stored as an ir.config_parameter (this Odoo instance's own database),
    # never in the module's source code — a shared secret hardcoded in a
    # .py file ships in cleartext with every install of this addon and in
    # the zip handed to each client, so it must be entered here instead,
    # out-of-band, by whoever sets up each Odoo instance. See controllers/sso.py.
    vita_bot_sso_secret = fields.Char(
        string='Vita Bot SSO Secret',
        config_parameter='cpbot_vita_bot_link.sso_secret',
        help='This Odoo instance\'s OWN secret for signing single-sign-on '
             'requests to the cpbot backend — every client gets a different '
             'one from Vita Care (not shared across clients), used as an '
             'HMAC signing key rather than sent as a plain header value. '
             'Get this value from Vita Care over a secure channel (not '
             'email/chat) — never commit or share it in a file.',
    )

    # Overridable per Odoo instance instead of hardcoded in controllers/sso.py
    # — lets a client point at a different backend/frontend (e.g. once
    # cpbot moves off the "-staging" URLs) without a code change or a new
    # module release. Blank falls back to the hardcoded defaults there.
    vita_bot_backend_url = fields.Char(
        string='Vita Bot Backend URL',
        config_parameter='cpbot_vita_bot_link.backend_url',
        help='The cpbot backend\'s SSO endpoint. Leave blank to use the '
             'module\'s built-in default.',
    )
    vita_bot_frontend_url = fields.Char(
        string='Vita Bot Frontend URL',
        config_parameter='cpbot_vita_bot_link.frontend_url',
        help='The cpbot frontend\'s SSO landing page. Leave blank to use '
             'the module\'s built-in default.',
    )

    # Each client's Odoo lives at {company-slug}.<this domain> (e.g.
    # test-life.vitacareonline.com) — the controller strips this suffix off
    # the current request's host to get the company slug, which cpbot then
    # looks up or auto-creates as a "company" grouping (see
    # _extract_company_slug_from_host in controllers/sso.py). Leave blank to
    # use the module's built-in default; only relevant for external client
    # instances (ignored when no client_key is set, i.e. Vita Care's own
    # internal Odoo).
    vita_bot_company_domain = fields.Char(
        string='Vita Bot Company Domain',
        config_parameter='cpbot_vita_bot_link.company_domain',
        help='The base domain each client\'s Odoo subdomain sits under '
             '(e.g. vitacareonline.com for test-life.vitacareonline.com). '
             'Leave blank to use the module\'s built-in default.',
    )
