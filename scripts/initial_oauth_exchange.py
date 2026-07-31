"""Run this ONCE, by hand, after a human completes the QBO browser consent step.

This script cannot run unattended: QBO's OAuth2 flow requires a human to
log into a QuickBooks company in a browser and click "Connect". This
script only performs the token exchange that comes *after* that click.

Usage:
    1. Build the consent URL (client_id/redirect_uri/scope) and open it in
       a browser. See docs/sandbox_test_procedure.md for the exact URL.
    2. Log in as the sandbox company, approve access.
    3. QBO redirects to QBO_REDIRECT_URI with ?code=...&realmId=... in the
       query string. Copy both values.
    4. Run:
       python scripts/initial_oauth_exchange.py --code <code> --realm-id <realmId>
    5. The script prints the realm ID (paste into .env as QBO_REALM_ID, if
       not already set) and writes the token cache file. It never prints
       the access or refresh token to the terminal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from erp_poc.qbo_auth import TokenStore, exchange_code_for_tokens  # noqa: E402
from erp_poc.settings import get_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", required=True, help="The `code` query param QBO redirected back with")
    parser.add_argument("--realm-id", required=True, help="The `realmId` query param QBO redirected back with")
    args = parser.parse_args()

    settings = get_settings()
    if args.realm_id != settings.qbo_realm_id:
        print(
            f"Warning: --realm-id ({args.realm_id}) does not match QBO_REALM_ID in "
            f"your .env ({settings.qbo_realm_id}). Update .env before continuing.",
            file=sys.stderr,
        )

    tokens = exchange_code_for_tokens(settings, authorization_code=args.code)
    store = TokenStore(settings.qbo_token_store_path)
    store.save(tokens)
    print(f"Token cache written to {settings.qbo_token_store_path}. Tokens are not printed.")
    print("Run `erp-poc verify-connection` next to confirm access.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
