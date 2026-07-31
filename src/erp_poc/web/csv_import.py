"""CSV parsing/validation for bulk customer/vendor upload.

Deliberately reuses `party_views.build_party_from_mapping` — the same
function that validates a single web-form submission — so a bulk-uploaded
row is checked against exactly the same rules as a manually-typed one.
CSV-specific concerns (file extension, non-CSV binary formats, row-count
limit, `is_active` spelled as "true"/"yes"/"1" rather than a checkbox's
"on") live only in this file.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from typing import Optional, Type

from ..canonical import CanonicalParty
from .party_views import build_party_from_mapping

REQUIRED_COLUMNS = ["display_name"]
KNOWN_COLUMNS = [
    "external_id",
    "display_name",
    "company_name",
    "email",
    "phone",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "postal_code",
    "country",
    "currency",
    "is_active",
]
_TRUTHY = {"true", "yes", "y", "1"}


@dataclass
class ParsedRow:
    row_number: int  # 1-based, counting data rows only (header excluded)
    data: dict
    party: Optional[CanonicalParty]
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.party is not None and not self.errors


class CsvValidationError(Exception):
    """A whole-file problem (wrong format, too many rows, missing columns) —
    distinct from a per-row validation error, which doesn't stop the file."""


def parse_and_validate_csv(
    raw_bytes: bytes, *, filename: str, model_cls: Type[CanonicalParty], max_rows: int
) -> list[ParsedRow]:
    if not filename.lower().endswith(".csv"):
        raise CsvValidationError("Only .csv files are accepted (not .xlsx, .xls, or other spreadsheet formats).")
    if raw_bytes[:2] == b"PK":
        raise CsvValidationError(
            "This looks like a spreadsheet file (e.g. Excel .xlsx), not a plain CSV. Export it as CSV and try again."
        )
    if b"\x00" in raw_bytes[:2048]:
        raise CsvValidationError("This file does not look like a plain-text CSV file.")

    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvValidationError("The file is not valid UTF-8 text.") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CsvValidationError("The file appears to be empty.")

    missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise CsvValidationError(f"The CSV is missing required column(s): {', '.join(missing)}.")

    rows: list[ParsedRow] = []
    for row_number, raw_row in enumerate(reader, start=1):
        if row_number > max_rows:
            raise CsvValidationError(f"This file has more than {max_rows} data rows. Split it into smaller files and upload separately.")

        normalized = dict(raw_row)
        normalized["is_active"] = "on" if str(raw_row.get("is_active", "")).strip().lower() in _TRUTHY else ""
        external_id = (raw_row.get("external_id") or "").strip() or str(uuid.uuid4())

        party, errors = build_party_from_mapping(model_cls, normalized, external_id=external_id)
        rows.append(ParsedRow(row_number=row_number, data=raw_row, party=party, errors=errors))

    if not rows:
        raise CsvValidationError("The file has a header row but no data rows.")

    return rows


def build_results_csv(results: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["row_number", "external_id", "display_name", "outcome", "qbo_id", "detail"])
    writer.writeheader()
    for r in results:
        writer.writerow(r)
    return buffer.getvalue()
