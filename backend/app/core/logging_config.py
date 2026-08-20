"""Minimal local-only operational logging.

Logs to stdout (visible in the uvicorn console) and to a local, git-ignored
file (backend/logs/app.log). Never configured to ship anywhere remote — no
remote log handler exists in this codebase.

Callers (see services/import_service.py) are responsible for only logging
operational facts (counts, ids, timing, success/failure) — this module does
not scrub messages, so never pass row content, filenames beyond the already
sanitized upload filename, or any finding/asset field into a log call.
"""
import logging
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    LOG_DIR.mkdir(exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    app_logger = logging.getLogger("adsec")
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(file_handler)
    app_logger.addHandler(console_handler)
    app_logger.propagate = False

    _configured = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"adsec.{name}")
