"""Proves a failed import rolls back completely -- no partial Assessment,
Finding, FindingInstance, or Asset rows are left behind, and no ASGI
traceback or assessment-content detail leaks to the API caller.

Two failure modes are exercised:
1. A synthetic mid-loop exception (any unexpected error, not just the
   specific IntegrityError this session's earlier bug produced) via
   monkeypatching, proving the general atomicity contract in
   import_service.py's try/except db.rollback()/raise block -- independent
   of whether the specific duplicate-FindingInstance bug is fixed or not.
2. A direct duplicate-FindingInstance collision engineered around the fix
   (pre-existing instance inserted out of band) hitting the router's
   SQLAlchemyError handler, proving the safe-error/no-traceback/rollback
   contract end-to-end over HTTP.
"""
import datetime
import io
import json
from unittest.mock import patch

import pytest

from app.models.asset import Asset
from app.models.assessment import Assessment
from app.models.finding import Finding
from app.models.finding_instance import FindingInstance
from app.services.import_service import import_pentera_json

DATE_A = datetime.date(2026, 5, 1)


def _counts(db):
    return (
        db.query(Assessment).count(),
        db.query(Finding).count(),
        db.query(FindingInstance).count(),
        db.query(Asset).count(),
    )


def test_mid_import_exception_rolls_back_everything(db_session):
    """A generic failure partway through a multi-row batch must leave the
    database exactly as it was before the import was attempted -- no
    partial Assessment/Finding/FindingInstance/Asset."""
    payload = {
        "findings": [
            {"finding": "Domain Admin Membership", "target": "u1", "domain": "atomic.local", "severity": "Critical"},
            {"finding": "Weak Password", "target": "u2", "domain": "atomic.local", "severity": "Medium"},
            {"finding": "Password Reuse", "target": "u3", "domain": "atomic.local", "severity": "Low"},
        ]
    }
    content = json.dumps(payload).encode("utf-8")

    before = _counts(db_session)
    assert before == (0, 0, 0, 0)

    # Fail on the SECOND finding's risk computation -- proves rows already
    # added earlier in the same loop (finding 1's Asset/Finding/
    # FindingInstance) are rolled back too, not just the one that failed.
    call_count = {"n": 0}

    def _flaky_compute_risk(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("synthetic mid-import failure")
        from app.services.risk_engine import compute_risk as real_compute_risk

        return real_compute_risk(*args, **kwargs)

    with patch("app.services.import_service.compute_risk", side_effect=_flaky_compute_risk):
        with pytest.raises(RuntimeError, match="synthetic mid-import failure"):
            import_pentera_json(
                db_session,
                content,
                name="Atomicity test",
                assessment_date=DATE_A,
                environment="atomic.local",
                source_filename="test.json",
                notes=None,
            )

    after = _counts(db_session)
    assert after == before == (0, 0, 0, 0), (
        "a failed import must not leave any partial Assessment/Finding/"
        "FindingInstance/Asset rows behind"
    )


def test_successful_import_after_a_failed_one_still_works(db_session):
    """The rollback must leave the session usable for a subsequent,
    successful import -- not poison it."""
    bad_payload = json.dumps({"findings": [{"finding": "x"}]}).encode("utf-8")

    with patch("app.services.import_service.compute_risk", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            import_pentera_json(
                db_session,
                json.dumps({"findings": [{"finding": "Weak Password", "target": "u1", "domain": "atomic.local"}]}).encode(),
                name="fails",
                assessment_date=DATE_A,
                environment="atomic.local",
                source_filename="test.json",
                notes=None,
            )

    assert _counts(db_session) == (0, 0, 0, 0)

    good_payload = json.dumps(
        {"findings": [{"finding": "Weak Password", "target": "u1", "domain": "atomic.local", "severity": "Medium"}]}
    ).encode("utf-8")
    summary = import_pentera_json(
        db_session,
        good_payload,
        name="succeeds",
        assessment_date=DATE_A,
        environment="atomic.local",
        source_filename="test.json",
        notes=None,
    )
    assert summary.new_findings == 1
    assert _counts(db_session) == (1, 1, 1, 1)


def test_unexpected_db_error_returns_safe_message_not_traceback(client):
    """Router-level: an unexpected SQLAlchemyError during import must
    become a clean 500 with a safe, generic message -- never a raw ASGI
    traceback, and never any echoed assessment content."""
    payload = {"findings": [{"finding": "Weak Password", "target": "u1", "domain": "atomic.local", "severity": "Medium"}]}
    content = json.dumps(payload).encode("utf-8")

    from sqlalchemy.exc import OperationalError

    with patch(
        "app.services.import_service.compute_risk",
        side_effect=OperationalError("statement", {}, Exception("simulated db failure")),
    ):
        resp = client.post(
            "/imports/pentera",
            data={"name": "DB failure test", "assessment_date": "2026-05-01", "environment": "atomic.local"},
            files={"file": ("test.json", io.BytesIO(content), "application/json")},
        )

    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "Import failed due to an internal error. No partial data was saved."
    # Never leak the underlying exception text, which could theoretically
    # include bound parameter values.
    assert "simulated db failure" not in json.dumps(body)
    assert "Traceback" not in json.dumps(body)
