import re
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.logging_config import get_logger
from app.integrations.pentera.parser import ParseError
from app.schemas.assessment import ImportSummaryOut
from app.services.import_service import import_pentera_csv, import_pentera_json

router = APIRouter(prefix="/imports", tags=["imports"])

log = get_logger("imports")

SUPPORTED_EXTENSIONS = (".csv", ".json")


def _sanitize_filename(filename: str) -> str:
    filename = filename.strip().replace("\\", "/").split("/")[-1]
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    return filename[:255] or "upload"


@router.post("/pentera", response_model=ImportSummaryOut)
async def import_pentera(
    name: str = Form(...),
    assessment_date: date = Form(...),
    environment: str | None = Form(None),
    notes: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # Fetched per-request (not a module-level global) so there is exactly
    # one place the limit is read from; get_settings() is itself
    # lru_cache'd, so this is cheap and still requires a process restart
    # to pick up an .env change — see docs/LOCAL_DATA_SECURITY.md's
    # "guaranteed restart" procedure.
    settings = get_settings()

    filename_lower = (file.filename or "").lower()
    if not filename_lower.endswith(SUPPORTED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail="Only .json or .csv files are supported (Pentera JSON or CSV export).",
        )
    is_json = filename_lower.endswith(".json")

    content = await file.read()
    detected_bytes = len(content)
    max_bytes = settings.max_upload_size_bytes
    if detected_bytes > max_bytes:
        # Byte counts only — never file contents, never the filename here
        # (that's logged separately, sanitized, once we're past this
        # check) — safe to log and safe to return to the client.
        log.warning(
            "Pentera upload rejected: detected_bytes=%d max_bytes=%d",
            detected_bytes,
            max_bytes,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Upload rejected: detected {detected_bytes} bytes; maximum {max_bytes} bytes.",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    safe_filename = _sanitize_filename(file.filename)

    import_fn = import_pentera_json if is_json else import_pentera_csv
    try:
        summary = import_fn(
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
