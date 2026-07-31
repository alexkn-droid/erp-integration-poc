"""Bulk CSV upload: validate the whole file -> preview -> confirm -> process
-> downloadable results. State lives in BulkUploadJob (DB), not memory, so
the flow survives a cold start between steps on Render's free tier.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from ...canonical import CanonicalCustomer, CanonicalVendor
from ...errors import ERPError
from ..csv_import import CsvValidationError, KNOWN_COLUMNS, ParsedRow, build_results_csv, parse_and_validate_csv
from ..deps import get_db, redirect_with_message, require_csrf, require_login, require_sandbox_environment
from ..messages import plain_language_message
from ..models_db import BulkUploadJob
from ..party_views import build_party_from_mapping
from ..qbo import build_party_service, get_qbo_client_or_none
from ..templating import render

router = APIRouter(prefix="/bulk-upload")

_MODEL_BY_ENTITY = {"customer": CanonicalCustomer, "vendor": CanonicalVendor}
_LABEL_BY_ENTITY = {"customer": "Customer", "vendor": "Vendor"}


@router.get("")
def bulk_upload_form(request: Request, session: dict = Depends(require_login)):
    web_settings = request.app.state.web_settings
    return render(
        request, "bulk_upload.html", session=session,
        max_rows=web_settings.max_upload_rows, columns=KNOWN_COLUMNS,
    )


@router.post("")
async def bulk_upload_submit(
    request: Request,
    entity_type: str = Form(...),
    csrf_token: str = Form(...),
    file: UploadFile | None = None,
    db: Session = Depends(get_db),
    session: dict = Depends(require_login),
):
    require_csrf(session, csrf_token)
    web_settings = request.app.state.web_settings

    if entity_type not in _MODEL_BY_ENTITY:
        return render(request, "bulk_upload.html", session=session, max_rows=web_settings.max_upload_rows, columns=KNOWN_COLUMNS, error="Choose Customer or Vendor.")
    if file is None or not file.filename:
        return render(request, "bulk_upload.html", session=session, max_rows=web_settings.max_upload_rows, columns=KNOWN_COLUMNS, error="Choose a CSV file to upload.")

    raw_bytes = await file.read()
    if len(raw_bytes) > web_settings.max_upload_bytes:
        return render(
            request, "bulk_upload.html", session=session, max_rows=web_settings.max_upload_rows, columns=KNOWN_COLUMNS,
            error=f"That file is too large. The limit is {web_settings.max_upload_bytes // 1024} KB.",
        )

    try:
        rows = parse_and_validate_csv(raw_bytes, filename=file.filename, model_cls=_MODEL_BY_ENTITY[entity_type], max_rows=web_settings.max_upload_rows)
    except CsvValidationError as exc:
        return render(request, "bulk_upload.html", session=session, max_rows=web_settings.max_upload_rows, columns=KNOWN_COLUMNS, error=str(exc))

    rows_json = [
        {
            "row_number": r.row_number,
            "data": dict(r.data),
            "errors": r.errors,
            "external_id": r.party.external_id if r.party else None,
            "display_name": r.party.display_name if r.party else r.data.get("display_name", ""),
        }
        for r in rows
    ]
    job = BulkUploadJob(entity_type=entity_type, filename=file.filename, row_count=len(rows), rows_json=rows_json)
    db.add(job)
    db.commit()
    db.refresh(job)

    return RedirectResponse(url=f"/bulk-upload/{job.id}/preview", status_code=303)


@router.get("/{job_id}/preview")
def bulk_preview(request: Request, job_id: str, db: Session = Depends(get_db), session: dict = Depends(require_login)):
    job = db.get(BulkUploadJob, job_id)
    if job is None:
        return RedirectResponse(url=redirect_with_message("/bulk-upload", "That upload was not found (it may have expired).", level="error"), status_code=303)

    valid_count = sum(1 for r in job.rows_json if not r["errors"])
    invalid_count = len(job.rows_json) - valid_count
    return render(
        request, "bulk_preview.html", session=session, job=job,
        label=_LABEL_BY_ENTITY[job.entity_type], valid_count=valid_count, invalid_count=invalid_count,
    )


@router.post("/{job_id}/confirm")
def bulk_confirm(
    request: Request,
    job_id: str,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    session: dict = Depends(require_login),
):
    require_csrf(session, csrf_token)
    require_sandbox_environment(request.app.state.web_settings)
    job = db.get(BulkUploadJob, job_id)
    if job is None:
        return RedirectResponse(url=redirect_with_message("/bulk-upload", "That upload was not found (it may have expired).", level="error"), status_code=303)
    if job.status != "pending_confirmation":
        return RedirectResponse(url=f"/bulk-upload/{job.id}/results", status_code=303)

    client = get_qbo_client_or_none(request, db)
    if client is None:
        return RedirectResponse(url=redirect_with_message("/connection", "QuickBooks is not connected. Connect it first.", level="warning"), status_code=303)

    model_cls = _MODEL_BY_ENTITY[job.entity_type]
    service = build_party_service(entity_type=job.entity_type, model_cls=model_cls, web_settings=request.app.state.web_settings, client=client, db=db)

    results = []
    try:
        for row in job.rows_json:
            if row["errors"]:
                results.append({
                    "row_number": row["row_number"], "external_id": row.get("external_id") or "",
                    "display_name": row.get("display_name", ""), "outcome": "failed",
                    "qbo_id": "", "detail": "; ".join(row["errors"]),
                })
                continue

            party, errors = build_party_from_mapping(model_cls, row["data"], external_id=row["external_id"])
            if party is None:
                results.append({
                    "row_number": row["row_number"], "external_id": row.get("external_id") or "",
                    "display_name": row.get("display_name", ""), "outcome": "failed",
                    "qbo_id": "", "detail": "; ".join(errors),
                })
                continue

            try:
                result = service.sync(party, approve=lambda p: True)
                results.append({
                    "row_number": row["row_number"], "external_id": party.external_id,
                    "display_name": party.display_name, "outcome": result.status,
                    "qbo_id": result.party.erp_id if result.party else "", "detail": "",
                })
            except ERPError as exc:
                results.append({
                    "row_number": row["row_number"], "external_id": party.external_id,
                    "display_name": party.display_name, "outcome": "failed",
                    "qbo_id": "", "detail": plain_language_message(exc),
                })
    finally:
        client.close()

    job.results_json = results
    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc)
    db.commit()

    return RedirectResponse(url=f"/bulk-upload/{job.id}/results", status_code=303)


@router.get("/{job_id}/results")
def bulk_results(request: Request, job_id: str, db: Session = Depends(get_db), session: dict = Depends(require_login)):
    job = db.get(BulkUploadJob, job_id)
    if job is None or job.results_json is None:
        return RedirectResponse(url=redirect_with_message("/bulk-upload", "That upload's results were not found.", level="error"), status_code=303)

    counts = {"created": 0, "already_exists": 0, "failed": 0}
    for r in job.results_json:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1

    return render(request, "bulk_results.html", session=session, job=job, label=_LABEL_BY_ENTITY[job.entity_type], counts=counts)


@router.get("/{job_id}/download")
def bulk_download(job_id: str, db: Session = Depends(get_db), session: dict = Depends(require_login)):
    job = db.get(BulkUploadJob, job_id)
    if job is None or job.results_json is None:
        return RedirectResponse(url="/bulk-upload", status_code=303)

    csv_text = build_results_csv(job.results_json)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="bulk_upload_{job.id}_results.csv"'},
    )
