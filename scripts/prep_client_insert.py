"""
Prepares an INSERT for odoo_client_connections: encrypts the client's Odoo
password AND generates+encrypts a fresh, unique SSO signing secret for this
client, then prints ready-to-run SQL. Does not touch the database itself —
copy the printed statement and run it manually.

Every client gets their OWN SSO secret (never shared across clients) — this
is what the cpbot_vita_bot_link Odoo module uses as an HMAC key to sign its
/auth/odoo-sso requests (see cpbot_vita_bot_link/controllers/sso.py and
main.py's _verify_odoo_sso_signature). The plaintext secret is printed ONCE
below — it cannot be retrieved later (only the encrypted form is stored) —
give it to the client over a secure out-of-band channel (never email/chat)
to paste into their Odoo's Settings > General Settings > Vita Bot page.

Usage:
    python scripts/prep_client_insert.py --client-name "Vita Care" \
        --client-key vita-care-prod --odoo-url https://client.odoo.com \
        --odoo-db client_db --odoo-username admin@client.com
    (you'll be prompted for the Odoo password; it is not echoed or logged)
"""
import argparse
import getpass
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.crypto import encrypt_value


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser(description="Prepare an INSERT statement for odoo_client_connections")
    parser.add_argument("--tenant-id", default=os.getenv("VITA_CARE_TENANT_ID"),
                         help="Tenant UUID (defaults to VITA_CARE_TENANT_ID from .env)")
    parser.add_argument("--client-name", required=True)
    parser.add_argument("--client-key", required=True, help="Unique key the Odoo module sends on SSO")
    parser.add_argument("--odoo-url", required=True)
    parser.add_argument("--odoo-db", required=True)
    parser.add_argument("--odoo-username", required=True)
    args = parser.parse_args()

    if not args.tenant_id:
        parser.error("--tenant-id not given and VITA_CARE_TENANT_ID is not set in .env")

    password = getpass.getpass("Odoo password for this client: ")
    if not password:
        parser.error("password cannot be empty")

    encrypted_password = encrypt_value(password)

    sso_secret = secrets.token_urlsafe(32)
    encrypted_sso_secret = encrypt_value(sso_secret)

    print("\n-- Run this against the database:\n")
    print(
        "INSERT INTO odoo_client_connections "
        "(tenant_id, client_name, client_key, odoo_url, odoo_db, odoo_username, "
        "odoo_password_encrypted, sso_secret_encrypted)\n"
        "VALUES (\n"
        f"    {_sql_quote(args.tenant_id)},\n"
        f"    {_sql_quote(args.client_name)},\n"
        f"    {_sql_quote(args.client_key)},\n"
        f"    {_sql_quote(args.odoo_url)},\n"
        f"    {_sql_quote(args.odoo_db)},\n"
        f"    {_sql_quote(args.odoo_username)},\n"
        f"    {_sql_quote(encrypted_password)},\n"
        f"    {_sql_quote(encrypted_sso_secret)}\n"
        ");"
    )
    print(
        f"\n-- Give this SSO secret to the client over a secure channel (never email/chat).\n"
        f"-- It cannot be retrieved again once you close this terminal.\n"
        f"-- They paste it into their Odoo's Settings > General Settings > Vita Bot > SSO Secret.\n"
        f"SSO secret: {sso_secret}"
    )


if __name__ == "__main__":
    main()
