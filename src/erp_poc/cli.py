"""Command-line entry point.

Every write command requires a human "yes" at the terminal unless --yes
is passed explicitly, which is only intended for scripted runs against a
sandbox realm you've already confirmed via QBO_ENVIRONMENT=sandbox.
This CLI refuses to run any write command when QBO_ENVIRONMENT=production.
"""

from __future__ import annotations

import argparse
import json
import sys

from pydantic import ValidationError

from .audit import AuditTrail
from .canonical import CanonicalCustomer
from .errors import ERPError
from .idempotency import IdempotencyStore
from .qbo_auth import TokenStore
from .qbo_client import QBOClient
from .service import CustomerSyncService
from .settings import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="erp-poc")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("verify-connection", help="Confirm OAuth + API access work end to end")

    read_parser = sub.add_parser("read-customer", help="Read one customer by QBO Id")
    read_parser.add_argument("--erp-id", required=True)
    read_parser.add_argument("--external-id", required=True, help="Our system's ID to tag the result with")

    create_parser = sub.add_parser("create-customer", help="Create (idempotently) a customer from a JSON file")
    create_parser.add_argument("--from-json", required=True, help="Path to a CanonicalCustomer JSON file")
    create_parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation prompt")

    args = parser.parse_args(argv)
    try:
        settings = get_settings()
    except ValidationError as exc:
        missing = ", ".join(e["loc"][0] for e in exc.errors())
        print(
            f"Missing required configuration: {missing}.\n"
            "Copy .env.example to .env and fill in real values (see README.md).",
            file=sys.stderr,
        )
        return 2

    if args.command != "verify-connection" and args.command != "read-customer":
        if settings.qbo_environment != "sandbox":
            print(
                "Refusing to run a write command: QBO_ENVIRONMENT is not 'sandbox'. "
                "This PoC is not authorized to write to a non-sandbox realm.",
                file=sys.stderr,
            )
            return 2

    token_store = TokenStore(settings.qbo_token_store_path)
    client = QBOClient(settings, token_store)

    try:
        if args.command == "verify-connection":
            info = client.verify_connection()
            print(json.dumps({"CompanyName": info.get("CompanyName"), "Id": info.get("Id")}, indent=2))
            return 0

        if args.command == "read-customer":
            service = _build_service(settings, client)
            result = service.read_customer(erp_id=args.erp_id, external_id=args.external_id)
            print(result.model_dump_json(indent=2))
            return 0

        if args.command == "create-customer":
            with open(args.from_json, "r", encoding="utf-8") as f:
                customer = CanonicalCustomer.model_validate(json.load(f))

            def approve(c: CanonicalCustomer) -> bool:
                if args.yes:
                    return True
                answer = input(
                    f"About to CREATE customer '{c.display_name}' "
                    f"(external_id={c.external_id}) in QBO sandbox realm "
                    f"{settings.qbo_realm_id}. Proceed? [y/N] "
                )
                return answer.strip().lower() == "y"

            service = _build_service(settings, client)
            result = service.sync_customer(customer, approve=approve)
            print(json.dumps({"status": result.status}, indent=2))
            if result.customer:
                print(result.customer.model_dump_json(indent=2))
            return 0 if result.status != "rejected_by_human" else 1

    except ERPError as exc:
        print(f"ERP error [{type(exc).__name__}]: {exc.message}", file=sys.stderr)
        return 1
    finally:
        client.close()

    return 0


def _build_service(settings, client) -> CustomerSyncService:
    idempotency_store = IdempotencyStore(settings.idempotency_store_path)
    audit_trail = AuditTrail(settings.audit_log_path)
    return CustomerSyncService(settings, client, idempotency_store, audit_trail)


if __name__ == "__main__":
    raise SystemExit(main())
