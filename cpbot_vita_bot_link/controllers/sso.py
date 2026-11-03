import hashlib
import hmac
import logging
import time
from urllib.parse import urlencode, urlparse

import requests
from markupsafe import escape
from werkzeug.utils import redirect as werkzeug_redirect
from werkzeug.wrappers import Response

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Fallback defaults, used only when the corresponding Settings > General
# Settings > Vita Bot field (vita_bot_backend_url / vita_bot_frontend_url) is
# left blank — see _config_url() below. Not secrets, so it's fine for these
# to be hardcoded; they're just the values this module ships with until an
# admin overrides them per instance without needing a new module release.
DEFAULT_BACKEND_SSO_URL = "https://vitabot.vitacareonline.com/api/auth/odoo-sso"
DEFAULT_FRONTEND_SSO_LOGIN_URL = "https://vitabot.vitacareonline.com/sso-login"
DEFAULT_COMPANY_DOMAIN = "vitacareonline.com"

# The shared secret is NOT hardcoded here — a value baked into this .py
# file ships in cleartext inside every copy of this addon, including the
# zip handed to each client, and ends up readable by anyone with filesystem
# access to their Odoo server. It's entered instead via Settings > General
# Settings > Vita Bot (stored as the ir.config_parameter read below), by
# whoever sets up each Odoo instance, over a secure out-of-band channel.
#
# This Odoo instance's own secret — every client gets a DIFFERENT one (so a
# leak of one client's secret can't be used to impersonate a different
# client), matched on the backend by client_key. It's used as an HMAC key to
# SIGN each request (see _sign_sso_request below), never sent as a bare
# header value the way the old scheme did.

# The cpbot backend can be a Render free/staging service that spins down
# when idle, so a request made just after a period of inactivity has to wait
# through a cold start (typically 10-60s) before it responds. Rather than one
# long single attempt, this is spread across several shorter attempts (see
# MAX_AUTO_RETRIES below) so no single HTTP request risks tripping a
# reverse-proxy/worker timeout, while the combined wait across attempts still
# comfortably covers the documented cold-start window.
#
# Each attempt still blocks one Odoo worker for up to SSO_REQUEST_TIMEOUT
# seconds — on a small Odoo deployment (few worker processes/threads), many
# users hitting SSO at once during a cold start can tie up every worker and
# make the whole Odoo instance briefly unresponsive to everyone, not just
# this feature. Kept short (not the previous 20s) specifically to bound that
# worst case; MAX_AUTO_RETRIES/AUTO_RETRY_DELAY_SECONDS raised to compensate
# so the total coverage is still comfortably past the ~60s cold-start window.
# If your Odoo deployment runs with very few workers, consider this when
# tuning further.
SSO_REQUEST_TIMEOUT = 8
MAX_AUTO_RETRIES = 9
AUTO_RETRY_DELAY_SECONDS = 3

ODOO_DEFAULT_BACKEND_PATH = "/web"  # Exists on every Odoo version — the safe fallback.

SSO_RETRYING_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"><title>Vita Bot</title>
  <meta http-equiv="refresh" content="{delay};url={retry_url}">
</head>
<body style="font-family: sans-serif; text-align: center; padding: 80px 20px; color: #333;">
  <h2>Vita Bot is waking up&hellip;</h2>
  <p>This can happen after a period of inactivity. Retrying automatically (attempt {attempt} of {max_attempts})&hellip;</p>
  <p><a href="{retry_url}">Click here if it doesn't retry on its own</a></p>
</body>
</html>"""

SSO_ERROR_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Vita Bot</title></head>
<body style="font-family: sans-serif; text-align: center; padding: 80px 20px; color: #333;">
  <h2>Vita Bot is still waking up</h2>
  <p>This can happen after a period of inactivity. Please wait a moment and click the Vita Bot icon again.</p>
  <p><a href="{back_url}">Back to Odoo</a></p>
</body>
</html>"""

SSO_NOT_CONFIGURED_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Vita Bot</title></head>
<body style="font-family: sans-serif; text-align: center; padding: 80px 20px; color: #333;">
  <h2>Vita Bot is not set up yet</h2>
  <p>An administrator needs to enter the SSO secret in
  Settings &gt; General Settings &gt; Vita Bot before this can be used.</p>
  <p><a href="{back_url}">Back to Odoo</a></p>
</body>
</html>"""

SSO_PORTAL_FORBIDDEN_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Vita Bot</title></head>
<body style="font-family: sans-serif; text-align: center; padding: 80px 20px; color: #333;">
  <h2>Vita Bot is for internal staff only</h2>
  <p>Portal users don't get a Vita Bot account.</p>
  <p><a href="{back_url}">Back to Odoo</a></p>
</body>
</html>"""

SSO_REJECTED_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Vita Bot</title></head>
<body style="font-family: sans-serif; text-align: center; padding: 80px 20px; color: #333;">
  <h2>Vita Bot could not sign you in</h2>
  <p>The backend rejected this request — this is a setup issue, not a
  temporary outage, so retrying won't help.</p>
  <p style="color: #900; font-family: monospace;">{reason}</p>
  <p>An administrator should check Settings &gt; General Settings &gt; Vita
  Bot (Client Key / SSO Secret) and confirm this company is set up on the
  cpbot backend.</p>
  <p><a href="{back_url}">Back to Odoo</a></p>
</body>
</html>"""


def _config_url(param: str, default: str) -> str:
    """Reads an admin-overridable URL from Settings > General Settings >
    Vita Bot (ir.config_parameter), falling back to this module's built-in
    default when left blank — see models/res_config_settings.py."""
    value = request.env["ir.config_parameter"].sudo().get_param(param)
    return value.strip() if value and value.strip() else default


def _retry_or_give_up(attempt_num: int) -> Response:
    """The shared tail of both retryable failure paths (transport error, or
    a 5xx/malformed response from an otherwise-reachable backend) — auto
    -refreshes up to MAX_AUTO_RETRIES times, then shows the final
    give-up page. NOT used for a definite 4xx rejection (see
    SSO_REJECTED_HTML above) — that's a config problem, not something a
    retry could ever fix."""
    if attempt_num < MAX_AUTO_RETRIES:
        retry_url = f"/vita_bot/sso?{urlencode({'attempt': attempt_num + 1})}"
        html = SSO_RETRYING_HTML.format(
            delay=AUTO_RETRY_DELAY_SECONDS,
            retry_url=retry_url,
            attempt=attempt_num + 1,
            max_attempts=MAX_AUTO_RETRIES,
        )
        return Response(html, status=200, content_type="text/html")
    html = SSO_ERROR_HTML.format(back_url=escape(_back_to_odoo_url()))
    return Response(html, status=502, content_type="text/html")


def _sign_sso_request(secret: str, client_key, odoo_user_id: int, email: str, username: str, company_slug, timestamp: str) -> str:
    """Must byte-for-byte match the canonical string the backend
    reconstructs and verifies in main.py's _verify_odoo_sso_signature — see
    that function's docstring for why each field is included."""
    canonical = f"{client_key or ''}\n{odoo_user_id}\n{email.lower()}\n{username}\n{company_slug or ''}\n{timestamp}"
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def _extract_company_slug_from_host(company_domain: str) -> str | None:
    """test-life.vitacareonline.com -> "test-life". None if the current
    request's host doesn't end with company_domain at all (e.g. Vita
    Care's own internal Odoo, or a bare/unexpected host during local dev) —
    callers should treat None as "don't touch company grouping", not as an
    empty slug to resolve."""
    host = request.httprequest.host.split(":")[0].lower()  # drop a :port if present
    suffix = f".{company_domain.lower().lstrip('.')}"
    if not host.endswith(suffix):
        return None
    slug = host[: -len(suffix)]
    return slug or None


def _back_to_odoo_url() -> str:
    """Where the error page's "Back to Odoo" link should point.

    Prefers the page the user actually came from (the Referer header, sent
    by the browser on the same-origin click that reached this controller —
    not user-suppliable like a query param would be), falling back to
    Odoo's own backend root when there's no referrer or it points somewhere
    else entirely (e.g. a bookmark or a link pasted from elsewhere).

    The Referer header's VALUE is still attacker-controlled (any client can
    send any Referer it likes), so the caller must HTML-escape this before
    interpolating it into a page — see the escape() calls at each call site
    below. Returned raw (not pre-escaped) because this function's job is
    picking the right URL, not presentation.
    """
    referrer = request.httprequest.referrer
    if referrer:
        own_host = urlparse(request.httprequest.host_url).netloc
        if urlparse(referrer).netloc == own_host:
            return referrer
    return ODOO_DEFAULT_BACKEND_PATH


class CpbotVitaBotSSOController(http.Controller):

    @http.route("/vita_bot/sso", type="http", auth="user", website=False, csrf=False)
    def vita_bot_sso(self, attempt="0", **kwargs):
        """Signs the current Odoo user into cpbot and hands the browser off
        to the frontend, already carrying a valid access token.

        auth="user" means Odoo itself bounces anonymous visitors to
        /web/login first, so request.env.user here is always a real,
        already-authenticated Odoo user.
        """
        try:
            attempt_num = int(attempt)
        except ValueError:
            attempt_num = 0
        # Clamp: a crafted/garbage ?attempt= (negative, huge, non-numeric)
        # must never change the retry bound below.
        attempt_num = max(0, min(attempt_num, MAX_AUTO_RETRIES))

        user = request.env.user

        # `share` is Odoo's own standard flag for "this is a portal/public
        # user, not an internal employee" — reject before anything else so
        # a portal user never gets a cpbot account created for them. (The
        # menu item itself is also now restricted to base.group_user, as
        # defense in depth — see views/cpbot_vita_bot_link_menu.xml — but a
        # portal user could still reach this URL directly if they knew it.)
        if user.share:
            html = SSO_PORTAL_FORBIDDEN_HTML.format(back_url=escape(_back_to_odoo_url()))
            return Response(html, status=403, content_type="text/html")

        email = user.login
        username = user.name
        odoo_user_id = user.id

        config = request.env["ir.config_parameter"].sudo()
        backend_url = _config_url("cpbot_vita_bot_link.backend_url", DEFAULT_BACKEND_SSO_URL)
        frontend_url = _config_url("cpbot_vita_bot_link.frontend_url", DEFAULT_FRONTEND_SSO_LOGIN_URL)

        # Set per-company in Settings > General Settings > Vita Bot — lets
        # the cpbot backend tell this company's Odoo data apart from any of
        # Vita Care's other client companies'. Left blank ONLY makes sense
        # for Vita Care's own internal Odoo instance — the backend now
        # rejects any other instance that omits it, rather than silently
        # falling back to Vita Care's own Odoo data (see main.py's
        # /auth/odoo-sso: client_key absent -> ODOO_SSO_INTERNAL_SECRET only).
        client_key = config.get_param("cpbot_vita_bot_link.client_key") or None

        # test-life.vitacareonline.com -> "test-life": cpbot looks this
        # company up (or auto-creates it) and assigns the user to it — no
        # manual per-client setup needed, unlike client_key above. None if
        # this request's host isn't under company_domain at all (e.g. Vita
        # Care's own internal instance, or local dev) — company grouping is
        # simply left untouched in that case.
        company_domain = _config_url("cpbot_vita_bot_link.company_domain", DEFAULT_COMPANY_DOMAIN)
        company_slug = _extract_company_slug_from_host(company_domain)

        sso_secret = config.get_param("cpbot_vita_bot_link.sso_secret")
        if not sso_secret:
            _logger.error("Vita Bot SSO: cpbot_vita_bot_link.sso_secret is not configured")
            html = SSO_NOT_CONFIGURED_HTML.format(back_url=escape(_back_to_odoo_url()))
            return Response(html, status=503, content_type="text/html")

        timestamp = str(int(time.time()))
        signature = _sign_sso_request(sso_secret, client_key, odoo_user_id, email, username, company_slug, timestamp)

        try:
            response = requests.post(
                backend_url,
                json={
                    "email": email,
                    "username": username,
                    "odoo_user_id": odoo_user_id,
                    "client_key": client_key,
                    "company_slug": company_slug,
                },
                headers={
                    "X-Odoo-Sso-Timestamp": timestamp,
                    "X-Odoo-Sso-Signature": signature,
                },
                timeout=SSO_REQUEST_TIMEOUT,
                # Never follow a redirect here — doing so would silently
                # re-send these signed headers to wherever the redirect
                # points, which may not be the trusted backend.
                allow_redirects=False,
            )
        except requests.RequestException:
            # Transport-level failure (timeout, connection refused, DNS,
            # TLS, ...) — this IS what a genuine cold start looks like, so
            # the "waking up" auto-retry is the right response.
            _logger.exception(
                "Vita Bot SSO: request failed for Odoo user %s (attempt %d)", email, attempt_num
            )
            return _retry_or_give_up(attempt_num)

        if 400 <= response.status_code < 500:
            # The backend is up and definitively REJECTED this exact
            # request (bad/unconfigured client_key, bad signature, unknown
            # company, ...) — not a cold start, and retrying identically 9
            # more times would only ever produce the same rejection while
            # showing the user a misleading "waking up" message the whole
            # time. Show the backend's own reason instead, once.
            try:
                reason = response.json().get("detail") or response.text
            except ValueError:
                reason = response.text or f"HTTP {response.status_code}"
            _logger.error(
                "Vita Bot SSO: backend rejected Odoo user %s: %s (status %d)",
                email, reason, response.status_code,
            )
            html = SSO_REJECTED_HTML.format(
                reason=escape(str(reason)[:300]), back_url=escape(_back_to_odoo_url()),
            )
            return Response(html, status=response.status_code, content_type="text/html")

        try:
            response.raise_for_status()
            # A short-lived, single-use exchange code — never the real
            # access token (see main.py's /auth/odoo-sso for why).
            code = response.json()["code"]
        except (requests.RequestException, ValueError, KeyError):
            # 5xx from the backend, or a 2xx with an unexpected body — both
            # genuinely worth retrying (a 5xx especially can be the backend
            # itself still finishing its own cold start).
            _logger.exception(
                "Vita Bot SSO: failed to sign in Odoo user %s (attempt %d)", email, attempt_num
            )
            return _retry_or_give_up(attempt_num)

        redirect_url = f"{frontend_url}?{urlencode({'code': code})}"
        return werkzeug_redirect(redirect_url, code=302)
