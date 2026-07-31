"""Generates the two secrets the web app needs: APP_SECRET_KEY and
SHARED_PASSWORD_HASH. Run this locally; paste the output into your local
.env for development, or into the hosting platform's environment-variable
UI for a deployment. Never paste secrets into a chat with an AI assistant,
a commit, or a log file — this script only prints to your own terminal.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from erp_poc.web.security import generate_app_secret_key, hash_password  # noqa: E402


def main() -> int:
    print("APP_SECRET_KEY=" + generate_app_secret_key())

    password = getpass.getpass("Choose the shared password for this app (input hidden): ")
    confirm = getpass.getpass("Confirm: ")
    if password != confirm:
        print("Passwords did not match. Nothing was hashed.", file=sys.stderr)
        return 1
    if len(password) < 8:
        print("Choose a password with at least 8 characters.", file=sys.stderr)
        return 1

    print("SHARED_PASSWORD_HASH=" + hash_password(password))
    print("\nCopy both lines above into your .env (local) or your hosting platform's")
    print("environment variable settings (deployed). The plaintext password is not")
    print("stored anywhere — write it down somewhere safe; it can't be recovered from the hash.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
