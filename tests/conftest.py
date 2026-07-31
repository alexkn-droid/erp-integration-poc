from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from erp_poc.settings import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        qbo_client_id="test-client-id",
        qbo_client_secret="test-client-secret",
        qbo_environment="sandbox",
        qbo_realm_id="1234567890",
        qbo_token_store_path=tmp_path / "tokens.json",
        idempotency_store_path=tmp_path / "idempotency.json",
        audit_log_path=tmp_path / "audit.log",
        max_retries=3,
        retry_base_delay_seconds=0.0,
    )
