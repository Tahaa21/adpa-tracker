"""Boundary tests for the /imports/pentera upload size limit.

Background: a real-world local test reported a ~60 KB Pentera JSON file
being rejected with a "File exceeds 10 MB" error. Diagnosis performed
(documented in the commit that added this file) found the size-limit
computation and comparison in app/core/config.py and
app/routers/imports.py to be mathematically and empirically correct:

    max_upload_size_bytes = max_upload_size_mb * 1024 * 1024
                           = 10 * 1024 * 1024
                           = 10,485,760 bytes (10 MiB)

Verified directly (Settings().max_upload_size_bytes == 10485760), via a
raw HTTP request against the running endpoint (a 67.8 KB synthetic JSON
file accepted with 200), and via the real browser UI using a real
File/DataTransfer-driven upload (a 107.8 KB synthetic JSON file accepted
with 200, 650 findings imported). No unit/comparison bug was found in the
current code — see the commit message for the full diagnostic trail. These
tests exist as permanent, precise regression coverage for this exact class
of bug (a missing `* 1024` factor, a KB/MB/MiB mix-up, an inverted
comparison, or any future change that accidentally reintroduces one),
covering both formats and the exact boundary.

Comparison semantics (documented behavior, not incidental): the check is
    if len(content) > settings.max_upload_size_bytes: reject
i.e. STRICT greater-than. A file of EXACTLY 10 MiB is therefore ACCEPTED,
not rejected — "10 MB max" means "up to and including 10 MiB". Only a file
one byte OVER 10 MiB is rejected.
"""
import io
import json

import pytest

MiB = 1024 * 1024
TEN_MIB = 10 * MiB  # 10,485,760 bytes — must match settings.max_upload_size_bytes


def _json_payload_of_size(target_bytes: int) -> bytes:
    """A single, real, parseable Pentera-JSON finding padded with a long
    description so the serialized payload is exactly `target_bytes` long.
    Used for the ACCEPT cases so we prove real end-to-end acceptance
    (parsed and imported), not just "the size check didn't reject it"."""
    base = {
        "findings": [
            {
                "finding": "Weak Password",
                "target": "user0",
                "domain": "test.local",
                "severity": "Medium",
                "description": "",
            }
        ]
    }
    base_len = len(json.dumps(base).encode())
    padding_needed = target_bytes - base_len
    assert padding_needed >= 0, "target_bytes too small for a valid single-finding payload"
    base["findings"][0]["description"] = "A" * padding_needed
    content = json.dumps(base).encode()
    assert len(content) == target_bytes, f"padding math off: got {len(content)}, wanted {target_bytes}"
    return content


def _csv_payload_of_size(target_bytes: int) -> bytes:
    """Real, parseable Pentera-CSV padded to an exact byte size via a
    handful of rows with a large-but-safe padded Notes field, NOT one
    single giant field — Python's csv module caps any single field at
    131072 bytes (csv.field_size_limit()'s default); a padding chunk well
    under that (50,000 bytes) keeps every field valid while needing only a
    couple hundred rows even at 10 MiB (fast to parse/import), instead of
    ~250,000 tiny rows (slow).

    Each row targets a DISTINCT asset (fixed-width zero-padded index) —
    deliberately not identical rows. Identical (duplicate finding+asset)
    rows within one file hit a separate, real, pre-existing bug
    (IntegrityError from a non-autoflushing session's stale
    already-exists check) that is out of scope for this fix; using
    distinct rows here avoids exercising it so these tests stay focused on
    the upload-size boundary only. See PR/commit notes for that bug.
    """
    header = b"Finding,Target,Domain,Severity,Notes\n"
    row_of = lambda i, pad: b"Weak Password,user%08d,test.local,Medium,%s\n" % (i, b"A" * pad)
    chunk = 50_000
    row_len = len(row_of(0, chunk))

    n_full_rows, remaining = divmod(target_bytes - len(header), row_len)
    min_pad = len(row_of(0, 0))  # row with zero padding bytes
    if 0 < remaining < min_pad and n_full_rows > 0:
        n_full_rows -= 1
        remaining += row_len

    rows = [row_of(i, chunk) for i in range(n_full_rows)]
    if remaining:
        pad_len = remaining - min_pad
        assert pad_len >= 0, "target_bytes too small for a valid final row"
        rows.append(row_of(n_full_rows, pad_len))

    content = header + b"".join(rows)
    assert len(content) == target_bytes, f"padding math off: got {len(content)}, wanted {target_bytes}"
    return content


def _post(client, filename: str, content: bytes, content_type: str):
    return client.post(
        "/imports/pentera",
        data={"name": "Size boundary test", "assessment_date": "2026-08-20", "environment": "test.local"},
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


# --- JSON boundary tests -----------------------------------------------------


def test_json_60kb_accepted(client):
    content = _json_payload_of_size(60 * 1024)
    resp = _post(client, "sixty_kb.json", content, "application/json")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] == 1


def test_json_1mb_accepted(client):
    content = _json_payload_of_size(1 * MiB)
    resp = _post(client, "one_mb.json", content, "application/json")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] == 1


def test_json_just_under_10mib_accepted(client):
    content = _json_payload_of_size(TEN_MIB - 1)
    resp = _post(client, "just_under_10mib.json", content, "application/json")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] == 1


def test_json_exactly_10mib_accepted(client):
    """Documented boundary behavior: EXACTLY 10 MiB is accepted (strict
    `>` comparison, not `>=`). This is the intended semantics of "10 MB
    max" — see module docstring."""
    content = _json_payload_of_size(TEN_MIB)
    resp = _post(client, "exactly_10mib.json", content, "application/json")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] == 1


def test_json_just_over_10mib_rejected(client):
    content = _json_payload_of_size(TEN_MIB + 1)
    resp = _post(client, "just_over_10mib.json", content, "application/json")
    assert resp.status_code == 400
    assert "exceeds" in resp.json()["detail"].lower()


# --- CSV boundary tests (same limit, same code path, must match JSON) -------


def test_csv_60kb_accepted(client):
    content = _csv_payload_of_size(60 * 1024)
    resp = _post(client, "sixty_kb.csv", content, "text/csv")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] > 0


def test_csv_1mb_accepted(client):
    content = _csv_payload_of_size(1 * MiB)
    resp = _post(client, "one_mb.csv", content, "text/csv")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] > 0


def test_csv_just_under_10mib_accepted(client):
    content = _csv_payload_of_size(TEN_MIB - 1)
    resp = _post(client, "just_under_10mib.csv", content, "text/csv")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] > 0


def test_csv_exactly_10mib_accepted(client):
    content = _csv_payload_of_size(TEN_MIB)
    resp = _post(client, "exactly_10mib.csv", content, "text/csv")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] > 0


def test_csv_just_over_10mib_rejected(client):
    content = _csv_payload_of_size(TEN_MIB + 1)
    resp = _post(client, "just_over_10mib.csv", content, "text/csv")
    assert resp.status_code == 400
    assert "exceeds" in resp.json()["detail"].lower()


# --- Direct unit check of the limit computation itself ----------------------


def test_settings_max_upload_size_bytes_is_exactly_10mib():
    """Pins the exact byte value so any future change to the MB->bytes
    conversion (e.g. a missing `* 1024`, or switching to decimal MB) is
    caught immediately, independent of any HTTP-level test above."""
    from app.core.config import Settings

    s = Settings(max_upload_size_mb=10)
    assert s.max_upload_size_bytes == 10_485_760 == TEN_MIB


@pytest.mark.parametrize("mb,expected_bytes", [(1, 1_048_576), (5, 5_242_880), (10, 10_485_760), (25, 26_214_400)])
def test_settings_max_upload_size_bytes_scales_correctly(mb, expected_bytes):
    from app.core.config import Settings

    assert Settings(max_upload_size_mb=mb).max_upload_size_bytes == expected_bytes
