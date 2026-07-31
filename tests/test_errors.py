from __future__ import annotations

from erp_poc.errors import (
    ERPAuthError,
    ERPDuplicateError,
    ERPNotFoundError,
    ERPPermissionError,
    ERPRateLimitError,
    ERPServerError,
    ERPValidationError,
    normalize_qbo_error,
)


def test_401_maps_to_auth_error():
    err = normalize_qbo_error(http_status=401, body=None)
    assert isinstance(err, ERPAuthError)
    assert err.retriable is False


def test_403_maps_to_permission_error():
    err = normalize_qbo_error(http_status=403, body=None)
    assert isinstance(err, ERPPermissionError)


def test_404_maps_to_not_found():
    err = normalize_qbo_error(http_status=404, body=None)
    assert isinstance(err, ERPNotFoundError)


def test_429_maps_to_rate_limit_and_is_retriable_with_retry_after():
    err = normalize_qbo_error(http_status=429, body=None, retry_after_header="12")
    assert isinstance(err, ERPRateLimitError)
    assert err.retriable is True
    assert err.retry_after_seconds == 12.0


def test_500_maps_to_server_error_and_is_retriable():
    err = normalize_qbo_error(http_status=500, body=None)
    assert isinstance(err, ERPServerError)
    assert err.retriable is True


def test_400_generic_maps_to_validation_error():
    body = {"Fault": {"Error": [{"Message": "Missing required field", "code": "2020"}], "type": "ValidationFault"}}
    err = normalize_qbo_error(http_status=400, body=body)
    assert isinstance(err, ERPValidationError)
    assert not isinstance(err, ERPDuplicateError)
    assert "Missing required field" in err.message


def test_400_duplicate_name_fault_maps_to_duplicate_error():
    body = {
        "Fault": {
            "Error": [
                {
                    "Message": "Duplicate Name Exists Error",
                    "Detail": "The name supplied already exists.",
                    "code": "6240",
                }
            ],
            "type": "ValidationFault",
        }
    }
    err = normalize_qbo_error(http_status=400, body=body)
    assert isinstance(err, ERPDuplicateError)
    assert "already exists" in err.message
    assert err.retriable is False


def test_malformed_retry_after_header_is_ignored_not_fatal():
    err = normalize_qbo_error(http_status=429, body=None, retry_after_header="not-a-number")
    assert isinstance(err, ERPRateLimitError)
    assert err.retry_after_seconds is None
