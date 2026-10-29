"""
Generates a fresh, unique SSO secret for an EXISTING client row in
odoo_client_connections and prints a ready-to-run UPDATE statement.
Does not touch the database itself — copy the printed statement and run it
manually (e.g. via psql).

Usage:
    python scripts/gen_client_sso_secret.py --client-key vita-care-erpeez
"""
import argparse
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.crypto import encrypt_value


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser(description="Generate a new SSO secret for an existing client")
    parser.add_argument("--client-key", required=True, help="The existing client_key in odoo_client_connections")
    args = parser.parse_args()

    sso_secret = secrets.token_urlsafe(32)
    encrypted_sso_secret = encrypt_value(sso_secret)

    print("\n-- Run this against the database:\n")
    print(
        "UPDATE odoo_client_connections\n"
        f"SET sso_secret_encrypted = {_sql_quote(encrypted_sso_secret)}\n"
        f"WHERE client_key = {_sql_quote(args.client_key)};"
    )
    print(
        f"\n-- Give this SSO secret to the client over a secure channel (never email/chat).\n"
        f"-- It cannot be retrieved again once you close this terminal.\n"
        f"-- They paste it into their Odoo's Settings > General Settings > Vita Bot > SSO Secret.\n"
        f"SSO secret: {sso_secret}"
    )


if __name__ == "__main__":
    main()