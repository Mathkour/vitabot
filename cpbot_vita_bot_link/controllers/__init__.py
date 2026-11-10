import logging

_logger = logging.getLogger(__name__)

# A crash while importing this controller (e.g. syntax the server's Python
# doesn't support) would otherwise abort loading the whole Odoo registry and
# take down every app on this database, not just Vita Bot. Log it and carry
# on: the Vita Bot menu then 404s until it's fixed, but Odoo keeps working.
try:
    from . import sso
except Exception:
    _logger.exception("Vita Bot Link: SSO controller failed to load; the Vita Bot menu is disabled until this is fixed")
