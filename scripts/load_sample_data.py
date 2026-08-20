#!/usr/bin/env python3
"""Loads the three sample Pentera assessments (2 CSV, 1 JSON) into a running
backend via the API — demonstrating both supported formats, including
cross-format deduplication (assessment 3's JSON findings recognize several
of assessment 2's CSV findings as the same logical issue).

Usage:
    python3 scripts/load_sample_data.py [API_BASE_URL]

Defaults to http://localhost:8000.
"""
import sys
from pathlib import Path
from urllib import request, error
import json
import mimetypes
import uuid

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample-data"

ASSESSMENTS = [
    {
        "file": "pentera_assessment_1_2026-05-15.csv",
        "name": "Fabrikam AD Assessment - May 2026",
        "assessment_date": "2026-05-15",
        "environment": "fabrikam.local",
        "notes": "Baseline Pentera assessment.",
    },
    {
        "file": "pentera_assessment_2_2026-07-15.csv",
        "name": "Fabrikam AD Assessment - July 2026",
        "assessment_date": "2026-07-15",
        "environment": "fabrikam.local",
        "notes": "Follow-up assessment after initial remediation push.",
    },
    {
        "file": "pentera_assessment_3_2026-09-15.json",
        "name": "Fabrikam AD Assessment - September 2026",
        "assessment_date": "2026-09-15",
        "environment": "fabrikam.local",
        "notes": "Third assessment, delivered as a Pentera JSON export.",
    },
]


def multipart_request(url: str, fields: dict, file_field: str, file_path: Path):
    boundary = uuid.uuid4().hex
    lines = []
    for key, value in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{key}"'.encode())
        lines.append(b"")
        lines.append(str(value).encode())

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    lines.append(f"--{boundary}".encode())
    lines.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"'.encode()
    )
    lines.append(f"Content-Type: {content_type}".encode())
    lines.append(b"")
    lines.append(file_path.read_bytes())
    lines.append(f"--{boundary}--".encode())
    lines.append(b"")

    body = b"\r\n".join(lines)
    req = request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    return req


def main() -> None:
    for entry in ASSESSMENTS:
        file_path = SAMPLE_DIR / entry["file"]
        if not file_path.exists():
            print(f"Missing sample file: {file_path}", file=sys.stderr)
            sys.exit(1)

        fields = {
            "name": entry["name"],
            "assessment_date": entry["assessment_date"],
            "environment": entry["environment"],
            "notes": entry["notes"],
        }
        req = multipart_request(f"{BASE_URL}/imports/pentera", fields, "file", file_path)
        try:
            with request.urlopen(req) as resp:
                summary = json.loads(resp.read())
                print(f"Imported {entry['file']}: {json.dumps(summary, indent=2)}")
        except error.HTTPError as exc:
            print(f"Failed to import {entry['file']}: {exc.code} {exc.read().decode()}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
