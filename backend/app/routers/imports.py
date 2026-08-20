import re
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.integrations.pentera.parser import ParseError
from app.schemas.assessment import ImportSummaryOut
from app.services.import_service import import_pentera_csv

router = APIRouter(prefix="/imports", tags=["imports"])

settings = get_settings()


def _sanitize_filename(filename: str) -> str:
    filename = filename.strip().replace("\\", "/").split("/")[-1]
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    return filename[:255] or "upload.csv"


@router.post("/pentera", response_model=ImportSummaryOut)
async def import_pentera(
    name: str = Form(...),
    assessment_date: date = Form(...),
    environment: str | None = Form(None),
    notes: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds max upload size of {settings.max_upload_size_mb}MB.",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    safe_filename = _sanitize_filename(file.filename)

    try:
        summary = import_pentera_csv(
            db,
            content,
            name=name,
            assessment_date=assessment_date,
            environment=environment,
            source_filename=safe_filename,
            notes=notes,
        )
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ImportSummaryOut(**summary.__dict__)
