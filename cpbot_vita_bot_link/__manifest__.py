{
    'name': 'Vita Bot Link',
    'version': '15.0.1.0.8',
    'category': 'Productivity',
    'summary': 'Adds a Vita Bot app icon that single-sign-on launches the Vita Care chatbot',
    'description': """
Vita Bot Link
=============
Adds a top-level app icon to Odoo's app switcher (alongside Knowledge,
Discuss, etc.), visible to internal users only. Clicking it:

1. Hits our own controller at /vita_bot/sso as the logged-in Odoo user
   (portal users are rejected — internal staff only).
2. That controller calls the cpbot backend's POST /auth/odoo-sso
   server-to-server, with the user's email, name, Odoo user id, and this
   company's client key (Settings > General Settings > Vita Bot), signing
   the whole request with this instance's own SSO secret. Backend
   auto-provisions a cpbot member account on first use, matched by a
   stable identity (client key + Odoo user id) rather than by email alone.
3. The backend hands back a short-lived, single-use code (never the real
   access token) in its response. The controller redirects the browser to
   the cpbot frontend's /sso-login?code=..., which immediately exchanges
   that code for the real token server-to-server — the token itself never
   rides in a URL, so it can't leak via browser history or access logs.

The client key is how Vita Care's Ask Odoo tells this company's Odoo data
apart from any of Vita Care's other client companies' — set it in Settings
> General Settings > Vita Bot before use. Leaving it blank is only valid
for Vita Care's own internal Odoo instance; any other instance that omits
it is rejected rather than silently falling back to Vita Care's own data.

If this Odoo instance's URL is a subdomain of the configured Company Domain
(default vitacareonline.com — e.g. test-life.vitacareonline.com), the
controller also extracts that subdomain as a company slug and sends it
along, signed the same way. cpbot looks up or auto-creates a matching
"company" grouping and assigns the signing-in user to it — no manual setup
needed beyond the client key/secret above.

Before this goes live, an administrator must also enter the SSO Secret in
that same Settings > General Settings > Vita Bot page — a value UNIQUE to
this company, given by Vita Care over a secure channel (never by email or
chat, and never committed to this module's source).
""",
    'author': 'Vita Care',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'views/res_config_settings_views.xml',
        'views/cpbot_vita_bot_link_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
