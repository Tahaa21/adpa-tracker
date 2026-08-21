"""Regression tests for intra-assessment finding deduplication.

Background: a real Pentera JSON import crashed with
    sqlalchemy.exc.IntegrityError: UNIQUE constraint failed:
    finding_instances.finding_id, finding_instances.assessment_id

Root cause: when two source records within the SAME import batch
normalized to the same logical Finding (identical records, or
superficially different ones sharing a fingerprint), the code checked for
an existing FindingInstance via a plain SELECT before INSERTing. Because
the session uses autoflush=False (see app/core/db.py), that SELECT could
not see the FIRST record's still-unflushed db.add(FindingInstance(...))
from earlier in the same loop, so the SECOND record's check incorrectly
returned "no existing instance" and attempted a second INSERT for the
same (finding_id, assessment_id) pair, violating the UNIQUE constraint.

Fix: track fingerprints already seen WITHIN THIS IMPORT BATCH in an
in-memory Python set (no DB round-trip, no autoflush-visibility problem
possible), checked before any Asset/Finding/FindingInstance work happens
for a row. A duplicate is coalesced (counted, not persisted a second
time) and explicitly NOT counted as new or recurring -- those describe
cross-assessment history, not repeats within one file. The
UNIQUE(finding_id, assessment_id) DB constraint itself is untouched and
still the ultimate guarantee; these tests prove the application-level
logic never attempts to violate it.
"""
import datetime
import json

from app.models.asset import Asset
from app.models.finding import Finding
from app.models.finding_instance import FindingInstance
from app.services.fingerprint import compute_fingerprint
from app.services.import_service import import_pentera_csv, import_pentera_json

DATE_A = datetime.date(2026, 5, 1)
DATE_B = datetime.date(2026, 7, 1)


def _import_json(db, payload: dict, name: str, assessment_date: datetime.date):
    content = json.dumps(payload).encode("utf-8")
    return import_pentera_json(
        db,
        content,
        name=name,
        assessment_date=assessment_date,
        environment="dedup.local",
        source_filename="test.json",
        notes=None,
    )


def _import_csv(db, content: bytes, name: str, assessment_date: datetime.date):
    return import_pentera_csv(
        db,
        content,
        name=name,
        assessment_date=assessment_date,
        environment="dedup.local",
        source_filename="test.csv",
        notes=None,
    )


# --- 1. Two identical JSON source records in one assessment -----------------


def test_two_identical_json_records_produce_one_instance_no_crash(db_session):
    payload = {
        "findings": [
            {"finding": "Domain Admin Membership", "target": "jsmith", "domain": "dedup.local", "severity": "Critical"},
            {"finding": "Domain Admin Membership", "target": "jsmith", "domain": "dedup.local", "severity": "Critical"},
        ]
    }
    summary = _import_json(db_session, payload, "A1", DATE_A)

    assert summary.rows_imported == 2  # both source records were processed
    assert summary.new_findings == 1  # but only one logical finding
    assert summary.recurring_findings == 0
    assert summary.duplicate_observations_coalesced == 1

    assert db_session.query(Finding).count() == 1
    assert db_session.query(FindingInstance).count() == 1
    assert any("coalesced" in w for w in summary.warnings)


# --- 2. Superficially different records, same fingerprint -------------------


def test_superficially_different_records_same_fingerprint_one_instance(db_session):
    """Same logical finding (same normalized_type/domain/asset) but
    different free text, severity casing, and exploitable flag -- must
    still collapse to one FindingInstance."""
    payload = {
        "findings": [
            {
                "finding": "Weak Password",
                "target": "svc_test",
                "domain": "dedup.local",
                "severity": "high",
                "description": "Cracked by module A.",
                "exploitable": True,
            },
            {
                "finding": "weak password",  # different casing
                "target": "svc_test",
                "domain": "dedup.local",
                "severity": "HIGH",
                "description": "Reported again via a different attack path.",
                "exploitable": False,
            },
        ]
    }
    summary = _import_json(db_session, payload, "A1", DATE_A)

    assert summary.new_findings == 1
    assert summary.duplicate_observations_coalesced == 1
    assert db_session.query(FindingInstance).count() == 1

    fp = compute_fingerprint("WEAK_PASSWORD", "dedup.local", "svc_test")
    finding = db_session.query(Finding).filter(Finding.fingerprint == fp).first()
    assert finding is not None


# --- 3 & 4. Cross-assessment recurring + intra-assessment duplicate ---------


def test_recurring_across_assessments_and_duplicate_within_one(db_session):
    # Assessment A: one finding, observed once.
    payload_a = {
        "findings": [
            {"finding": "Domain Admin Membership", "target": "jsmith", "domain": "dedup.local", "severity": "Critical"},
        ]
    }
    summary_a = _import_json(db_session, payload_a, "A1", DATE_A)
    assert summary_a.new_findings == 1
    assert summary_a.recurring_findings == 0
    assert summary_a.duplicate_observations_coalesced == 0

    # Assessment B: the SAME logical finding appears TWICE (duplicate
    # within this assessment) -- must still be exactly one FindingInstance
    # for assessment B, correctly counted as "recurring" (existed in A),
    # not "new", and the second occurrence coalesced as a duplicate, not
    # double-counted as recurring either.
    payload_b = {
        "findings": [
            {"finding": "Domain Admin Membership", "target": "jsmith", "domain": "dedup.local", "severity": "Critical"},
            {"finding": "Domain Admin Membership", "target": "jsmith", "domain": "dedup.local", "severity": "Critical"},
        ]
    }
    summary_b = _import_json(db_session, payload_b, "A2", DATE_B)

    assert summary_b.new_findings == 0
    assert summary_b.recurring_findings == 1  # counted exactly once, not twice
    assert summary_b.duplicate_observations_coalesced == 1

    # Exactly one logical Finding, exactly two FindingInstances total
    # (one per assessment) -- not three.
    assert db_session.query(Finding).count() == 1
    assert db_session.query(FindingInstance).count() == 2

    fp = compute_fingerprint("DOMAIN_ADMIN_MEMBERSHIP", "dedup.local", "jsmith")
    finding = db_session.query(Finding).filter(Finding.fingerprint == fp).first()
    assert len(finding.instances) == 2
    instance_assessment_ids = {i.assessment_id for i in finding.instances}
    assert len(instance_assessment_ids) == 2  # one per assessment, not two in one


# --- 6. CSV duplicate behavior matches JSON ----------------------------------


def test_csv_duplicate_rows_within_one_assessment_coalesced(db_session):
    csv_content = (
        b"Finding,Target,Domain,Severity\n"
        b"Weak Password,svc_dup,dedup.local,Medium\n"
        b"Weak Password,svc_dup,dedup.local,Medium\n"
        b"Weak Password,svc_dup,dedup.local,Medium\n"
    )
    summary = _import_csv(db_session, csv_content, "C1", DATE_A)

    assert summary.rows_imported == 3
    assert summary.new_findings == 1
    assert summary.duplicate_observations_coalesced == 2
    assert db_session.query(FindingInstance).count() == 1


# --- 7. Cross-format deduplication still correct -----------------------------


def test_cross_format_duplicate_within_json_after_csv_baseline(db_session):
    """A finding first seen via CSV, then re-observed (with an intra-file
    duplicate) via a later JSON assessment -- proves the fingerprint-based
    intra-batch dedup composes correctly with the pre-existing
    cross-format/cross-assessment dedup."""
    csv_content = b"Finding,Target,Domain,Severity\nWeak Password,svc_x,dedup.local,Medium\n"
    _import_csv(db_session, csv_content, "C1", DATE_A)

    payload_b = {
        "findings": [
            {"finding": "Weak Password", "target": "svc_x", "domain": "dedup.local", "severity": "Medium"},
            {"finding": "Weak Password", "target": "svc_x", "domain": "dedup.local", "severity": "Medium"},
        ]
    }
    summary_b = _import_json(db_session, payload_b, "J1", DATE_B)

    assert summary_b.new_findings == 0
    assert summary_b.recurring_findings == 1
    assert summary_b.duplicate_observations_coalesced == 1
    assert db_session.query(Finding).count() == 1
    assert db_session.query(FindingInstance).count() == 2
    assert db_session.query(Asset).count() == 1
