"""Orchestration layer: this is the "workflow" described in the PoC spec.

`PartySyncService.sync()` implements the full create loop:
  1. Idempotency check (local store, then a live duplicate-name query).
  2. Human approval gate before any write.
  3. Create (with retry/backoff for transient failures).
  4. Read-back to confirm the ERP's view matches what we sent.
  5. Audit trail entry for the outcome either way.

`.update()` implements the equivalent update loop, re-reading the record
immediately before writing to minimize the window in which its SyncToken
could go stale (QBO's optimistic-concurrency check).

This is the one place ERP-specific (qbo_client, transform_qbo) and
ERP-agnostic (canonical, idempotency, audit, retry) pieces meet. A second
connector would provide its own qbo_client/transform_qbo-equivalent pair
and reuse everything else in this file's shape. `CustomerSyncService` and
`VendorSyncService` are thin, named subclasses fixing `entity_type` /
`model_cls` — kept separate so CLI code and existing tests calling
`.sync_customer()` / `.read_customer()` are unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from .audit import AuditTrail
from .canonical import CanonicalCustomer, CanonicalParty, CanonicalVendor
from .errors import ERPDuplicateError
from .idempotency import IdempotencyStore
from .qbo_client import QBOClient
from .retry import call_with_retry
from .settings import Settings
from .transform_qbo import party_to_qbo_payload, qbo_data_to_party

PartyT = TypeVar("PartyT", bound=CanonicalParty)


@dataclass
class SyncResult(Generic[PartyT]):
    status: str  # "created", "already_exists", "rejected_by_human", "updated"
    party: PartyT | None

    @property
    def customer(self) -> PartyT | None:
        """Backward-compatible alias for code/tests written before Vendor support existed."""
        return self.party


class PartySyncService:
    def __init__(
        self,
        settings: Settings,
        client: QBOClient,
        idempotency_store: IdempotencyStore,
        audit_trail: AuditTrail,
        *,
        entity_type: str,
        model_cls: type[CanonicalParty],
    ) -> None:
        self._settings = settings
        self._client = client
        self._idempotency = idempotency_store
        self._audit = audit_trail
        self._entity_type = entity_type
        self._model_cls = model_cls

    @property
    def object_type(self) -> str:
        return self._entity_type[:1].upper() + self._entity_type[1:]

    def read(self, *, erp_id: str, external_id: str) -> CanonicalParty:
        data = call_with_retry(
            lambda: self._client.get_entity(self._entity_type, erp_id),
            max_retries=self._settings.max_retries,
            base_delay_seconds=self._settings.retry_base_delay_seconds,
        )
        return qbo_data_to_party(data, external_id=external_id, model_cls=self._model_cls)

    def search(self, *, name_contains: str = "", max_results: int = 25) -> list[CanonicalParty]:
        matches = call_with_retry(
            lambda: self._client.search_entities(self._entity_type, name_contains=name_contains, max_results=max_results),
            max_retries=self._settings.max_retries,
            base_delay_seconds=self._settings.retry_base_delay_seconds,
        )
        return [qbo_data_to_party(m, external_id=str(m["Id"]), model_cls=self._model_cls) for m in matches]

    def sync(self, party: CanonicalParty, *, approve: Callable[[CanonicalParty], bool]) -> SyncResult:
        existing_erp_id = self._idempotency.get(party.external_id)
        if existing_erp_id:
            result = self.read(erp_id=existing_erp_id, external_id=party.external_id)
            self._audit.record(
                action=f"sync_{self._entity_type}",
                object_type=self.object_type,
                external_id=party.external_id,
                erp_id=existing_erp_id,
                result="already_exists (local idempotency hit)",
                human_approved=False,
            )
            return SyncResult(status="already_exists", party=result)

        live_match = call_with_retry(
            lambda: self._client.find_entity_by_display_name(self._entity_type, party.display_name),
            max_retries=self._settings.max_retries,
            base_delay_seconds=self._settings.retry_base_delay_seconds,
        )
        if live_match is not None:
            self._idempotency.put(party.external_id, str(live_match["Id"]))
            result = qbo_data_to_party(live_match, external_id=party.external_id, model_cls=self._model_cls)
            self._audit.record(
                action=f"sync_{self._entity_type}",
                object_type=self.object_type,
                external_id=party.external_id,
                erp_id=result.erp_id,
                result="already_exists (live DisplayName match)",
                human_approved=False,
            )
            return SyncResult(status="already_exists", party=result)

        if not approve(party):
            self._audit.record(
                action=f"sync_{self._entity_type}",
                object_type=self.object_type,
                external_id=party.external_id,
                erp_id=None,
                result="rejected_by_human",
                human_approved=False,
            )
            return SyncResult(status="rejected_by_human", party=None)

        payload = party_to_qbo_payload(party)
        try:
            created = call_with_retry(
                lambda: self._client.create_entity(self._entity_type, payload),
                max_retries=self._settings.max_retries,
                base_delay_seconds=self._settings.retry_base_delay_seconds,
            )
        except ERPDuplicateError:
            # Race: something else created it between our check and our write.
            live_match = self._client.find_entity_by_display_name(self._entity_type, party.display_name)
            if live_match is None:
                raise
            created = live_match

        self._idempotency.put(party.external_id, str(created["Id"]))
        confirmed = self.read(erp_id=str(created["Id"]), external_id=party.external_id)
        self._audit.record(
            action=f"sync_{self._entity_type}",
            object_type=self.object_type,
            external_id=party.external_id,
            erp_id=confirmed.erp_id,
            result="created",
            human_approved=True,
        )
        return SyncResult(status="created", party=confirmed)

    def update(
        self,
        *,
        erp_id: str,
        party: CanonicalParty,
        approve: Callable[[CanonicalParty], bool],
    ) -> SyncResult:
        """Update an existing record. `party.external_id` is used only for audit/read-back."""
        current = self.read(erp_id=erp_id, external_id=party.external_id)

        if not approve(party):
            self._audit.record(
                action=f"update_{self._entity_type}",
                object_type=self.object_type,
                external_id=party.external_id,
                erp_id=erp_id,
                result="rejected_by_human",
                human_approved=False,
            )
            return SyncResult(status="rejected_by_human", party=None)

        payload = party_to_qbo_payload(party)
        payload["Id"] = erp_id
        payload["SyncToken"] = current.erp_sync_token

        try:
            updated = call_with_retry(
                lambda: self._client.update_entity(self._entity_type, payload),
                max_retries=self._settings.max_retries,
                base_delay_seconds=self._settings.retry_base_delay_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - re-raise after audit, any failure is worth recording
            self._audit.record(
                action=f"update_{self._entity_type}",
                object_type=self.object_type,
                external_id=party.external_id,
                erp_id=erp_id,
                result=f"failed ({type(exc).__name__})",
                human_approved=True,
            )
            raise

        confirmed = self.read(erp_id=str(updated["Id"]), external_id=party.external_id)
        self._audit.record(
            action=f"update_{self._entity_type}",
            object_type=self.object_type,
            external_id=party.external_id,
            erp_id=confirmed.erp_id,
            result="updated",
            human_approved=True,
        )
        return SyncResult(status="updated", party=confirmed)


class CustomerSyncService(PartySyncService):
    def __init__(self, settings: Settings, client: QBOClient, idempotency_store: IdempotencyStore, audit_trail: AuditTrail) -> None:
        super().__init__(settings, client, idempotency_store, audit_trail, entity_type="customer", model_cls=CanonicalCustomer)

    def read_customer(self, *, erp_id: str, external_id: str) -> CanonicalCustomer:
        return self.read(erp_id=erp_id, external_id=external_id)  # type: ignore[return-value]

    def sync_customer(self, customer: CanonicalCustomer, *, approve: Callable[[CanonicalCustomer], bool]) -> SyncResult:
        return self.sync(customer, approve=approve)  # type: ignore[arg-type]


class VendorSyncService(PartySyncService):
    def __init__(self, settings: Settings, client: QBOClient, idempotency_store: IdempotencyStore, audit_trail: AuditTrail) -> None:
        super().__init__(settings, client, idempotency_store, audit_trail, entity_type="vendor", model_cls=CanonicalVendor)

    def read_vendor(self, *, erp_id: str, external_id: str) -> CanonicalVendor:
        return self.read(erp_id=erp_id, external_id=external_id)  # type: ignore[return-value]

    def sync_vendor(self, vendor: CanonicalVendor, *, approve: Callable[[CanonicalVendor], bool]) -> SyncResult:
        return self.sync(vendor, approve=approve)  # type: ignore[arg-type]
