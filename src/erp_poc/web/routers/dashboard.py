from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db, require_login
from ..models_db import ActivityLog
from ..qbo import get_connection_status
from ..templating import render

router = APIRouter()


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), session: dict = Depends(require_login)):
    status = get_connection_status(db)
    recent = db.execute(select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(10)).scalars().all()
    return render(request, "dashboard.html", session=session, status=status, recent=recent)
