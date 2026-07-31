from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db, require_login
from ..models_db import ActivityLog
from ..templating import render

router = APIRouter()

_PAGE_SIZE = 50


@router.get("/activity")
def activity_history(request: Request, page: int = 1, db: Session = Depends(get_db), session: dict = Depends(require_login)):
    page = max(1, page)
    entries = (
        db.execute(
            select(ActivityLog)
            .order_by(ActivityLog.timestamp.desc())
            .offset((page - 1) * _PAGE_SIZE)
            .limit(_PAGE_SIZE + 1)
        )
        .scalars()
        .all()
    )
    has_next = len(entries) > _PAGE_SIZE
    entries = entries[:_PAGE_SIZE]
    return render(request, "activity.html", session=session, entries=entries, page=page, has_next=has_next)
