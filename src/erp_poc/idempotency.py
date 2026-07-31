"""Local idempotency map: our `external_id` -> QBO `Id`.

QBO's Accounting API has no native idempotency-key header (unlike, say,
Stripe). We compensate at the application layer two ways, used together
in service.py:

1. Before creating, check this local store for a prior mapping.
2. Before creating, also query QBO by DisplayName (belt-and-suspenders,
   and it's what catches the case where a previous run created the
   record but crashed before the mapping was persisted locally).

This is a flat JSON file for the POC. A production version would use a
real database row with a unique constraint on external_id.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class IdempotencyStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def get(self, external_id: str) -> Optional[str]:
        return self._load().get(external_id)

    def put(self, external_id: str, erp_id: str) -> None:
        data = self._load()
        data[external_id] = erp_id
        self._save(data)

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
