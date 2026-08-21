"""Boundary tests for the /imports/pentera upload size limit.

Background: a real-world local test reported a ~60 KB Pentera JSON file
being rejected with a "File exceeds max upload size of 10 MB" error, and
this persisted even after an earlier fix attempt. Root cause: the code's
size computation/comparison was (and remains) mathematically correct, but
the effective limit on a real local checkout is controlled by the
gitignored, locally-modified `.env` file's `MAX_UPLOAD_SIZE_MB` value,
which `git pull` never touches. `.env` files created early in this
project's life have `MAX_UPLOAD_SIZE_MB=10` baked in from the old default
and silently override any change made to the tracked default or
`.env.example`. See docs/LOCAL_DATA_SECURITY.md for the explicit
guaranteed-restart procedure this requires (updating the value alone,
without restarting the backend process, is not enough either — see below).

The limit is now 100 MiB by default (`max_upload_size_mb = 100` in
app/core/config.py, `.env.example`, and docker-compose.yml — one
authoritative value, read via `Settings.max_upload_size_bytes`, not
duplicated as a magic number anywhere else):

    max_upload_size_bytes = max_upload_size_mb * 1024 * 1024
                           = 100 * 1024 * 1024
                           = 104,857,600 bytes (100 MiB)

Comparison semantics (documented behavior, not incidental): the check in
routers/imports.py is
    if len(content) > settings.max_upload_size_bytes: reject
i.e. STRICT greater-than, evaluated against the actual bytes read (never
Content-Length or any other header/proxy). A file of EXACTLY 100 MiB is
therefore ACCEPTED, not rejected — "100 MB max" means "up to and
including 100 MiB". Only a file one byte OVER is rejected, and the
rejection response/log includes the exact detected and maximum byte
counts (never file contents or other metadata).

IMPORTANT — why editing .env is not enough by itself: app/core/config.py's
get_settings() is `@lru_cache`'d, and routers/imports.py additionally used
to cache a module-level `settings = get_settings()` at import time (now
fetched per-request instead, but the underlying get_settings() cache
still means the .env file is only ever read once per process). A backend
process that was already running when .env changed will keep using the
OLD value until it is actually killed and restarted — `git pull` alone,
or even editing .env alone, does not update a live process. See the
"Guaranteed restart" procedure this commit adds to
docs/LOCAL_DATA_SECURITY.md.
"""
import io
import json

import pytest

MiB = 1024 * 1024
HUNDRED_MIB = 100 * MiB  # 104,857,600 bytes — must match settings.max_upload_size_bytes


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
    under that (100,000 bytes) keeps every field valid while needing only
    ~1000 rows even at 100 MiB (fast to parse/import), instead of millions
    of tiny rows (slow).

    Each row targets a DISTINCT asset (fixed-width zero-padded index) —
    deliberately not identical rows. Identical (duplicate finding+asset)
    rows within one file hit a separate, real, pre-existing bug
    (IntegrityError from a non-autoflushing session's stale
    already-exists check) that is out of scope for this fix; using
    distinct rows here avoids exercising it so these tests stay focused on
    the upload-size boundary only.
    """
    header = b"Finding,Target,Domain,Severity,Notes\n"
    row_of = lambda i, pad: b"Weak Password,user%08d,test.local,Medium,%s\n" % (i, b"A" * pad)
    chunk = 100_000
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


# --- JSON boundary tests, exact sizes requested -----------------------------


@pytest.mark.parametrize(
    "label,size",
    [
        ("60kb", 60 * 1024),
        ("1mb", 1 * MiB),
        ("20mb", 20 * MiB),
        ("60mb", 60 * MiB),
    ],
)
def test_json_accepted_at_requested_sizes(client, label, size):
    content = _json_payload_of_size(size)
    resp = _post(client, f"{label}.json", content, "application/json")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] == 1


def test_json_just_under_100mib_accepted(client):
    content = _json_payload_of_size(HUNDRED_MIB - 1)
    resp = _post(client, "just_under_100mib.json", content, "application/json")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] == 1


def test_json_exactly_100mib_accepted(client):
    """Documented boundary behavior: EXACTLY 100 MiB is accepted (strict
    `>` comparison, not `>=`). This is the intended semantics of "100 MB
    max" — see module docstring."""
    content = _json_payload_of_size(HUNDRED_MIB)
    resp = _post(client, "exactly_100mib.json", content, "application/json")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] == 1


def test_json_just_over_100mib_rejected_with_exact_byte_counts(client):
    content = _json_payload_of_size(HUNDRED_MIB + 1)
    resp = _post(client, "just_over_100mib.json", content, "application/json")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    # Exact, safe error format: real detected/maximum byte counts, no file
    # contents or other metadata.
    assert f"detected {HUNDRED_MIB + 1} bytes" in detail
    assert f"maximum {HUNDRED_MIB} bytes" in detail


# --- CSV boundary tests (same limit, same code path, must match JSON) -------


@pytest.mark.parametrize(
    "label,size",
    [
        ("60kb", 60 * 1024),
        ("1mb", 1 * MiB),
        ("20mb", 20 * MiB),
        ("60mb", 60 * MiB),
    ],
)
def test_csv_accepted_at_requested_sizes(client, label, size):
    content = _csv_payload_of_size(size)
    resp = _post(client, f"{label}.csv", content, "text/csv")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] > 0


def test_csv_just_under_100mib_accepted(client):
    content = _csv_payload_of_size(HUNDRED_MIB - 1)
    resp = _post(client, "just_under_100mib.csv", content, "text/csv")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] > 0


def test_csv_exactly_100mib_accepted(client):
    content = _csv_payload_of_size(HUNDRED_MIB)
    resp = _post(client, "exactly_100mib.csv", content, "text/csv")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows_imported"] > 0


def test_csv_just_over_100mib_rejected_with_exact_byte_counts(client):
    content = _csv_payload_of_size(HUNDRED_MIB + 1)
    resp = _post(client, "just_over_100mib.csv", content, "text/csv")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert f"detected {HUNDRED_MIB + 1} bytes" in detail
    assert f"maximum {HUNDRED_MIB} bytes" in detail


# --- The exact string reported in the bug MUST NOT be producible anymore ----


def test_old_10mb_message_is_gone(client):
    """Regression guard for the exact reported symptom: neither the old
    message text nor a 10 MiB rejection can occur for a 60 KB file."""
    content = _json_payload_of_size(60 * 1024)
    resp = _post(client, "sixty_kb_regression.json", content, "application/json")
    assert resp.status_code == 200
    # (A 400 here at all would already be wrong; belt-and-suspenders check
    # that if anything ever regresses, it isn't the old message.)


# --- Direct unit check of the limit computation itself ----------------------


def test_settings_max_upload_size_bytes_is_exactly_100mib():
    """Pins the exact byte value so any future change to the MB->bytes
    conversion (e.g. a missing `* 1024`, or switching to decimal MB) is
    caught immediately, independent of any HTTP-level test above."""
    from app.core.config import Settings

    s = Settings(max_upload_size_mb=100)
    assert s.max_upload_size_bytes == 104_857_600 == HUNDRED_MIB


def test_settings_default_is_100mb():
    """The field default itself (used when no .env/env var overrides it)
    must be 100, not the old 10 — this is the actual fix, not just the
    conversion math."""
    from app.core.config import Settings

    assert Settings.model_fields["max_upload_size_mb"].default == 100


@pytest.mark.parametrize(
    "mb,expected_bytes",
    [(1, 1_048_576), (5, 5_242_880), (10, 10_485_760), (60, 62_914_560), (100, 104_857_600)],
)
def test_settings_max_upload_size_bytes_scales_correctly(mb, expected_bytes):
    from app.core.config import Settings

    assert Settings(max_upload_size_mb=mb).max_upload_size_bytes == expected_bytes
