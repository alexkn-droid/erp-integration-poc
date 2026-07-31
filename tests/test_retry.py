from __future__ import annotations

import pytest

from erp_poc.errors import ERPRateLimitError, ERPServerError, ERPValidationError
from erp_poc.retry import call_with_retry


def test_succeeds_on_first_try_without_sleeping():
    sleeps: list[float] = []
    result = call_with_retry(lambda: 42, sleep=sleeps.append)
    assert result == 42
    assert sleeps == []


def test_retries_retriable_error_then_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ERPServerError("boom", http_status=500)
        return "ok"

    sleeps: list[float] = []
    result = call_with_retry(flaky, max_retries=5, base_delay_seconds=0.01, sleep=sleeps.append)
    assert result == "ok"
    assert calls["n"] == 3
    assert len(sleeps) == 2


def test_does_not_retry_non_retriable_error():
    calls = {"n": 0}

    def always_bad():
        calls["n"] += 1
        raise ERPValidationError("bad request", http_status=400)

    with pytest.raises(ERPValidationError):
        call_with_retry(always_bad, max_retries=5, sleep=lambda _: None)
    assert calls["n"] == 1


def test_gives_up_after_max_retries():
    calls = {"n": 0}

    def always_throttled():
        calls["n"] += 1
        raise ERPRateLimitError("throttled", http_status=429)

    with pytest.raises(ERPRateLimitError):
        call_with_retry(always_throttled, max_retries=2, base_delay_seconds=0.0, sleep=lambda _: None)
    assert calls["n"] == 3  # first attempt + 2 retries


def test_honors_retry_after_over_backoff():
    calls = {"n": 0}
    sleeps: list[float] = []

    def once_throttled():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ERPRateLimitError("throttled", http_status=429, retry_after_seconds=5.0)
        return "ok"

    call_with_retry(once_throttled, base_delay_seconds=100.0, max_delay_seconds=30.0, sleep=sleeps.append)
    assert sleeps == [5.0]
