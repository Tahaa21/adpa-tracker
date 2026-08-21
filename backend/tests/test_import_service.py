import datetime

from app.models.finding import Finding
from app.models.finding_instance import FindingInstance
from app.services.import_service import import_pentera_csv

DATE_1 = datetime.date(2026, 5, 1)
DATE_2 = datetime.date(2026, 7, 1)

ASSESSMENT_1_CSV = (
    b"Finding,Severity,Target,Object Type,Domain,Exploitable\n"
    b"Password Not Required,High,svc_backup,service_account,corp.local,false\n"
    b"Domain Admin Membership,Critical,jsmith,user,corp.local,true\n"
    b"Weak Password,Medium,jbrown,user,corp.local,false\n"
)

# svc_backup and jbrown findings recur; jsmith finding is now absent
# (resolved); a brand new finding (rjones) appears.
ASSESSMENT_2_CSV = (
    b"Finding,Severity,Target,Object Type,Domain,Exploitable\n"
    b"Password Not Required,High,svc_backup,service_account,corp.local,false\n"
    b"Weak Password,Medium,jbrown,user,corp.local,false\n"
    b"Weak Password,High,rjones,user,corp.local,true\n"
)


def _import(db, content, name, assessment_date):
    return import_pentera_csv(
        db,
        content,
        name=name,
        assessment_date=assessment_date,
        environment="corp.local",
        source_filename="test.csv",
        notes=None,
    )


def test_first_import_creates_findings_and_instances(db_session):
    summary = _import(db_session, ASSESSMENT_1_CSV, "A1", DATE_1)
    assert summary.rows_imported == 3
    assert summary.new_findings == 3
    assert summary.recurring_findings == 0
    assert summary.resolved_findings == 0

    findings = db_session.query(Finding).all()
    assert len(findings) == 3
    assert all(f.currently_present for f in findings)

    instances = db_session.query(FindingInstance).all()
    assert len(instances) == 3


def test_repeated_import_reuses_finding_for_recurring_issue(db_session):
    _import(db_session, ASSESSMENT_1_CSV, "A1", DATE_1)
    findings_after_1 = {f.fingerprint: f.id for f in db_session.query(Finding).all()}

    summary = _import(db_session, ASSESSMENT_2_CSV, "A2", DATE_2)

    assert summary.new_findings == 1  # rjones weak password
    assert summary.recurring_findings == 2  # svc_backup and jbrown recur
    assert summary.resolved_findings == 1  # jsmith domain admin no longer observed

    findings_after_2 = db_session.query(Finding).all()
    # Still only 4 logical findings total: the 3 original + 1 new one.
    assert len(findings_after_2) == 4

    # The recurring finding kept its identity (same row id) across imports.
    from app.services.fingerprint import compute_fingerprint

    recurring_fp = compute_fingerprint("PASSWORD_NOT_REQUIRED", "corp.local", "svc_backup", "Password Not Required")
    assert findings_after_1[recurring_fp] == (
        db_session.query(Finding).filter(Finding.fingerprint == recurring_fp).first().id
    )

    # It now has two FindingInstance rows (one per assessment).
    recurring_finding = db_session.query(Finding).filter(Finding.fingerprint == recurring_fp).first()
    assert len(recurring_finding.instances) == 2


def test_resolved_finding_marked_not_currently_present(db_session):
    _import(db_session, ASSESSMENT_1_CSV, "A1", DATE_1)
    _import(db_session, ASSESSMENT_2_CSV, "A2", DATE_2)

    from app.services.fingerprint import compute_fingerprint

    resolved_fp = compute_fingerprint("DOMAIN_ADMIN_MEMBERSHIP", "corp.local", "jsmith", "Domain Admin Membership")
    resolved_finding = db_session.query(Finding).filter(Finding.fingerprint == resolved_fp).first()
    assert resolved_finding.currently_present is False
    # First/last seen still reflect when it *was* observed, for history.
    assert resolved_finding.first_seen == DATE_1
    assert resolved_finding.last_seen == DATE_1


def test_reimporting_a_validated_finding_reopens_it(db_session):
    _import(db_session, ASSESSMENT_1_CSV, "A1", DATE_1)

    from app.services.fingerprint import compute_fingerprint

    fp = compute_fingerprint("PASSWORD_NOT_REQUIRED", "corp.local", "svc_backup", "Password Not Required")
    finding = db_session.query(Finding).filter(Finding.fingerprint == fp).first()
    finding.status = "VALIDATED"
    db_session.commit()

    _import(db_session, ASSESSMENT_2_CSV, "A2", DATE_2)

    db_session.refresh(finding)
    assert finding.status == "REOPENED"
