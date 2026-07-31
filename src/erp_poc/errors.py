"""Normalized error hierarchy.

QBO reports failures in two different shapes (an HTTP-level failure with
no body, and a 200/400-level response carrying a `Fault` JSON object with
its own internal codes) and the meaning of a given HTTP status varies by
context. `normalize_qbo_error` is the single place that knows about that
and converts it into one of the exceptions below, so the rest of the
codebase (retry logic, CLI, service layer) only ever has to reason about
this small, ERP-agnostic set.
"""

from __future__ import annotations

from typing import Any, Optional


class ERPError(Exception):
    """Base class for all normalized ERP errors."""

    retriable: bool = False

    def __init__(
        self,
        message: str,
        *,
        http_status: Optional[int] = None,
        code: Optional[str] = None,
        retry_after_seconds: Optional[float] = None,
        raw: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        self.raw = raw

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{type(self).__name__}(message={self.message!r}, http_status={self.http_status}, code={self.code})"


class ERPAuthError(ERPError):
    """Access token missing, expired, or revoked. Human must re-authorize."""

    retriable = False


class ERPPermissionError(ERPError):
    """Authenticated, but the connected app/user lacks the required scope or role."""

    retriable = False


class ERPValidationError(ERPError):
    """The request was rejected as business-invalid (bad/missing field, etc.)."""

    retriable = False


class ERPDuplicateError(ERPValidationError):
    """A record with a colliding unique key (e.g. DisplayName) already exists."""


class ERPConflictError(ERPValidationError):
    """The record was changed by someone/something else since it was last read

    (QBO's "Stale Object Error" — the SyncToken sent no longer matches the
    current one). Not retriable automatically: the caller must re-read the
    record and let a human decide whether to reapply their change.
    """


class ERPNotFoundError(ERPError):
    retriable = False


class ERPRateLimitError(ERPError):
    """Caller is being throttled. Safe to retry after backing off."""

    retriable = True


class ERPServerError(ERPError):
    """5xx from the ERP. Safe to retry with backoff."""

    retriable = True


class ERPNetworkError(ERPError):
    """Transport-level failure (timeout, DNS, connection reset). Safe to retry."""

    retriable = True


# QBO Fault "code" values we specifically recognize. Anything else falls
# back to a generic ERPValidationError so unknown faults still surface
# clearly instead of being swallowed.
_DUPLICATE_NAME_FAULT_CODE = "6240"


def normalize_qbo_error(
    *,
    http_status: int,
    body: Optional[dict] = None,
    retry_after_header: Optional[str] = None,
) -> ERPError:
    """Translate a QBO HTTP response into a normalized ERPError.

    `body` is the parsed JSON body if one was present (QBO error bodies
    look like: {"Fault": {"Error": [{"Message": ..., "Detail": ...,
    "code": ...}], "type": "..."}}).
    """
    retry_after = _parse_retry_after(retry_after_header)
    fault_errors = (body or {}).get("Fault", {}).get("Error", []) if body else []
    first = fault_errors[0] if fault_errors else {}
    code = str(first.get("code")) if first.get("code") is not None else None
    message = first.get("Message") or f"QBO request failed with HTTP {http_status}"
    detail = first.get("Detail")
    full_message = f"{message}: {detail}" if detail else message

    if http_status == 401:
        return ERPAuthError(full_message, http_status=http_status, code=code, raw=body)
    if http_status == 403:
        return ERPPermissionError(full_message, http_status=http_status, code=code, raw=body)
    if http_status == 404:
        return ERPNotFoundError(full_message, http_status=http_status, code=code, raw=body)
    if http_status == 429:
        return ERPRateLimitError(
            full_message, http_status=http_status, code=code, retry_after_seconds=retry_after, raw=body
        )
    if http_status >= 500:
        return ERPServerError(full_message, http_status=http_status, code=code, raw=body)
    if http_status == 400:
        if code == _DUPLICATE_NAME_FAULT_CODE:
            return ERPDuplicateError(full_message, http_status=http_status, code=code, raw=body)
        if "stale object" in full_message.lower():
            return ERPConflictError(full_message, http_status=http_status, code=code, raw=body)
        return ERPValidationError(full_message, http_status=http_status, code=code, raw=body)

    return ERPError(full_message, http_status=http_status, code=code, raw=body)


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
