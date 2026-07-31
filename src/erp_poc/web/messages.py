"""Translates internal errors into the plain-language messages end users see.

The raw exception message (which may echo QBO's own fault text) is always
logged server-side for developers; only these fixed, safe strings reach
the browser.
"""

from __future__ import annotations

from ..errors import (
    ERPAuthError,
    ERPConflictError,
    ERPDuplicateError,
    ERPError,
    ERPNotFoundError,
    ERPPermissionError,
    ERPRateLimitError,
)


def plain_language_message(exc: ERPError) -> str:
    if isinstance(exc, ERPAuthError):
        return "QuickBooks needs to be reconnected. Go to QuickBooks Connection and click Reconnect."
    if isinstance(exc, ERPPermissionError):
        return "The connected QuickBooks user doesn't have permission to do that."
    if isinstance(exc, ERPConflictError):
        return "This record was changed by someone else since you loaded it. Reload it and try again."
    if isinstance(exc, ERPDuplicateError):
        return "A record with this name already exists in QuickBooks."
    if isinstance(exc, ERPNotFoundError):
        return "That record could not be found in QuickBooks."
    if isinstance(exc, ERPRateLimitError):
        return "QuickBooks is temporarily limiting requests. Please wait a moment and try again."
    return "QuickBooks rejected this request. Please check the values and try again."
