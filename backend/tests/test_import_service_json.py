"""Import-service-level tests for the JSON path — mirrors
test_import_service.py's CSV tests to prove the two formats share the same
dedup/trend-tracking behavior end to end (they share the same mapper and
_import_parsed_rows core; this test proves that in practice, not just in
theory)."""
import datetime
import json

from app.models.finding import Finding
from app.models.finding_instance import FindingInstance
from app.services.import_service import import_pentera_json

DATE_1 = datetime.date(2026, 5, 1)
DATE_2 = datetime.date(2026, 7, 1)

# svc_backup and jbrown findings recur; jsmith finding is now absent
# (resolved); a brand new finding (rjones) appears -- same scenario as the
# CSV regression test, expressed as JSON instead.
ASSESSMENT_1_JSON = json.dumps(
    {
        "findings": [
            {"finding": "Password Not Required", "severity": "High", "target": "svc_backup", "objectType": "service_account", "domain": "corp.local", "exploitable": False},
            {"finding": "Domain Admin Membership", "severity": "Critical", "target": "jsmith", "objectType": "user", "domain": "corp.local", "exploitable": True},
            {"finding": "Weak Password", "severity": "Medium", "target": "jbrown", "objectType": "user", "domain": "corp.local", "exploitable": False},
        ]
    }
).encode("utf-8")

ASSESSMENT_2_JSON = json.dumps(
    {
        "findings": [
            {"finding": "Password Not Required", "severity": "High", "target": "svc_backup", "objectType": "service_account", "domain": "corp.local", "exploitable": False},
            {"finding": "Weak Password", "severity": "Medium", "target": "jbrown", "objectType": "user", "domain": "corp.local", "exploitable": False},
            {"finding": "Weak Password", "severity": "High", "target": "rjones", "objectType": "user", "domain": "corp.local", "exploitable": True},
        ]
    }
).encode("utf-8")


def _import(db, content, name, assessment_date):
    return import_pentera_json(
        db,
        content,
        name=name,
        assessment_date=assessment_date,
        environment="corp.local",
        source_filename="test.json",
        notes=None,
    )


def test_json_first_import_creates_findings_and_instances(db_session):
    summary = _import(db_session, ASSESSMENT_1_JSON, "A1", DATE_1)
    assert summary.rows_imported == 3
    assert summary.new_findings == 3
    assert summary.recurring_findings == 0
    assert summary.resolved_findings == 0
    assert summary.unknown_mappings == 0

    findings = db_session.query(Finding).all()
    assert len(findings) == 3
    assert all(f.currently_present for f in findings)

    instances = db_session.query(FindingInstance).all()
    assert len(instances) == 3


def test_json_repeated_import_dedups_same_as_csv_path(db_session):
    _import(db_session, ASSESSMENT_1_JSON, "A1", DATE_1)
    findings_after_1 = {f.fingerprint: f.id for f in db_session.query(Finding).all()}

    summary = _import(db_session, ASSESSMENT_2_JSON, "A2", DATE_2)

    assert summary.new_findings == 1  # rjones weak password
    assert summary.recurring_findings == 2  # svc_backup and jbrown recur
    assert summary.resolved_findings == 1  # jsmith domain admin no longer observed

    from app.services.fingerprint import compute_fingerprint

    recurring_fp = compute_fingerprint("PASSWORD_NOT_REQUIRED", "corp.local", "svc_backup", "Password Not Required")
    assert findings_after_1[recurring_fp] == (
        db_session.query(Finding).filter(Finding.fingerprint == recurring_fp).first().id
    )
    recurring_finding = db_session.query(Finding).filter(Finding.fingerprint == recurring_fp).first()
    assert len(recurring_finding.instances) == 2


def test_json_unknown_finding_type_imported_not_discarded(db_session):
    content = json.dumps(
        {"findings": [{"finding": "Some Totally Novel Pentera Check Name", "target": "host1", "domain": "corp.local"}]}
    ).encode("utf-8")
    summary = _import(db_session, content, "A1", DATE_1)
    assert summary.rows_imported == 1
    assert summary.unknown_mappings == 1

    finding = db_session.query(Finding).first()
    assert finding.normalized_type == "UNKNOWN"
    assert finding.title == "Some Totally Novel Pentera Check Name"


def test_json_finding_missing_both_title_and_asset_is_skipped(db_session):
    content = json.dumps({"findings": [{"severity": "High"}]}).encode("utf-8")
    summary = _import(db_session, content, "A1", DATE_1)
    assert summary.rows_processed == 1
    assert summary.rows_imported == 0
    assert summary.rows_skipped == 1
    assert any("skipped" in w for w in summary.warnings)
