"""Retry helper with exponential backoff + jitter.

Only errors explicitly marked `retriable = True` (rate limits, 5xx,
network failures) are retried. Business/validation errors are never
retried, since retrying a malformed request just wastes the rate-limit
budget and delays surfacing a real problem to a human.
"""

from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

from .errors import ERPError

T = TypeVar("T")


def call_with_retry(
    fn: Callable[[], T],
    *,
    max_retries: int = 5,
    base_delay_seconds: float = 1.0,
    max_delay_seconds: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call `fn`, retrying on retriable ERPError instances.

    `max_retries` is the number of *additional* attempts after the first
    one, so max_retries=5 means up to 6 total calls to `fn`.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except ERPError as exc:
            if not exc.retriable or attempt >= max_retries:
                raise
            delay = _backoff_delay(attempt, base_delay_seconds, max_delay_seconds, exc.retry_after_seconds)
            sleep(delay)
            attempt += 1


def _backoff_delay(
    attempt: int,
    base_delay_seconds: float,
    max_delay_seconds: float,
    retry_after_seconds: float | None,
) -> float:
    if retry_after_seconds is not None:
        return min(retry_after_seconds, max_delay_seconds)
    exp_delay = base_delay_seconds * (2**attempt)
    jitter = random.uniform(0, base_delay_seconds)
    return min(exp_delay + jitter, max_delay_seconds)
