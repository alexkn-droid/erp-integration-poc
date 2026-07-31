"""Append-only audit trail.

Every attempted write (and its outcome) is recorded here, independent of
the application logs, so "who created/changed what, when, and was it
human-approved" can be answered without grepping log files. Never write
secrets (tokens, client secret) into this trail.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class AuditTrail:
    def __init__(self, path: Path) -> None:
        self._path = path

    def record(
        self,
        *,
        action: str,
        object_type: str,
        external_id: str,
        erp_id: Optional[str],
        result: str,
        human_approved: bool,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "object_type": object_type,
            "external_id": external_id,
            "erp_id": erp_id,
            "result": result,
            "human_approved": human_approved,
            "detail": detail or {},
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
