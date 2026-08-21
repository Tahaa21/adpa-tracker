"""Tests for Pentera ADPA JSON `achievements` handling.

All fixtures here are SYNTHETIC data shaped like the one sanitized real
`achievements` object we were given (values replaced by placeholders,
structure real):

    {
        "id": "example",
        "creation_time": "example",
        "name": "Password(s) stored in reversible encryption",
        "summary": [],
        "severity": 8.3,
        "parameters": {"Domain": "example"}
    }

No real Pentera export or real enterprise data is used anywhere in this
file — per explicit instruction, the real assessment was never requested
or inspected. See docs/PENTERA_IMPORT.md "Architecture: achievements vs.
vulnerabilities" for the design this proves.
"""
import json

from app.integrations.pentera.json_parser import parse_json
from app.integrations.pentera.mapper import map_rows
from app.models.finding import Finding
from app.models.finding_instance import FindingInstance
from app.services.import_service import import_pentera_json
from app.services.redaction import REDACTED_MARKER


def _achievement(
    name: str,
    severity: float,
    *,
    achievement_id: str = "achv-example",
    domain: str = "fabrikam.local",
    creation_time: str = "2026-08-01T00:00:00Z",
    summary: list | None = None,
    extra_parameters: dict | None = None,
) -> dict:
    params = {"Domain": domain}
    if extra_parameters:
        params.update(extra_parameters)
    return {
        "id": achievement_id,
        "creation_time": creation_time,
        "name": name,
        "summary": summary if summary is not None else [],
        "severity": severity,
        "parameters": params,
    }


def _vulnerability(i: int, domain: str = "fabrikam.local") -> dict:
    return {"id": f"vuln-{i}", "name": f"Low level observation {i}", "severity": 3.1, "parameters": {"Domain": domain}}


def _bytes(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


# --- (1) & (2): achievements chosen over vulnerabilities, not by size ------


def test_achievements_and_vulnerabilities_both_present_achievements_selected():
    data = {
        "achievements": [_achievement("Password(s) stored in reversible encryption", 8.3)],
        "vulnerabilities": [_vulnerability(i) for i in range(50)],
    }
    rows, warnings, counts = parse_json(_bytes(data))

    # Achievements (the smaller collection) was selected as the findings
    # source, NOT vulnerabilities (the much larger collection) -- proves
    # selection is by explicit known-collection priority, not size.
    assert len(rows) == 1
    assert rows[0].title == "Password(s) stored in reversible encryption"
    assert counts["achievements_discovered"] == 1
    assert counts["vulnerabilities_discovered"] == 50
    assert any("Achievements collection identified" in w for w in warnings)
    assert any("Vulnerabilities collection found (50 items)" in w for w in warnings)


def test_achievements_selected_even_when_vastly_smaller_than_vulnerabilities():
    # Mirrors the real-world discovery that prompted this change: 15,982
    # achievements vs. 15,259 vulnerabilities were close in size, but the
    # selection logic must not depend on relative size AT ALL -- verify
    # with vulnerabilities ~100x larger than achievements.
    data = {
        "achievements": [_achievement("Domain Admin Membership", 9.5, achievement_id="a1")],
        "vulnerabilities": [_vulnerability(i) for i in range(300)],
    }
    rows, _, counts = parse_json(_bytes(data))
    assert len(rows) == 1
    assert counts["achievements_discovered"] == 1
    assert counts["vulnerabilities_discovered"] == 300


# --- (3): numeric severity preserved and bucketed ---------------------------


def test_numeric_severity_preserved_and_bucketed():
    data = {"achievements": [_achievement("Password(s) stored in reversible encryption", 8.3)]}
    rows, _, _ = parse_json(_bytes(data))
    assert rows[0].severity == "8.3"

    result = map_rows(rows)
    nf = result.findings[0]
    # 8.3 falls in the 7.0-8.9 band -> "high" (see mapper.py
    # NUMERIC_SEVERITY_THRESHOLDS; explicitly NOT a CVSS claim).
    assert nf.severity == "high"
    # Original numeric value is never discarded.
    assert nf.source_metadata["pentera_numeric_severity"] == 8.3


def test_numeric_severity_bucket_boundaries():
    cases = [(9.2, "critical"), (7.0, "high"), (4.5, "medium"), (1.0, "low")]
    for value, expected_bucket in cases:
        data = {"achievements": [_achievement("Some Achievement", value)]}
        rows, _, _ = parse_json(_bytes(data))
        result = map_rows(rows)
        assert result.findings[0].severity == expected_bucket, f"severity {value} expected {expected_bucket}"


# --- (4): parameters.Domain handled ------------------------------------------


def test_parameters_domain_mapped_to_domain_field():
    data = {"achievements": [_achievement("Password Policy Weakness", 5.0, domain="fabrikam.local")]}
    rows, _, _ = parse_json(_bytes(data))
    assert rows[0].domain == "fabrikam.local"
    # No specific affected-object parameter beyond Domain -> domain-level
    # scope, same convention as a CSV domain-scoped finding.
    assert rows[0].asset_name == "fabrikam.local"
    assert rows[0].asset_type == "domain"


def test_parameters_with_specific_account_scope():
    data = {
        "achievements": [
            _achievement(
                "Weak Password",
                6.8,
                domain="fabrikam.local",
                extra_parameters={"Account": "svc_backup"},
            )
        ]
    }
    rows, _, _ = parse_json(_bytes(data))
    assert rows[0].asset_name == "svc_backup"
    assert rows[0].asset_type == "user"
    assert rows[0].domain == "fabrikam.local"


# --- (5): duplicate achievements coalesce with occurrence_count -------------


def test_duplicate_achievements_coalesce_into_one_finding_with_occurrence_count(db_session):
    data = {
        "achievements": [
            _achievement("Password(s) stored in reversible encryption", 8.3, achievement_id="a1"),
            _achievement("Password(s) stored in reversible encryption", 8.3, achievement_id="a2"),
            _achievement("Password(s) stored in reversible encryption", 8.3, achievement_id="a3"),
        ]
    }
    content = _bytes(data)
    import datetime

    summary = import_pentera_json(
        db_session, content, name="A1", assessment_date=datetime.date(2026, 8, 1),
        environment="fabrikam.local", source_filename="synthetic.json", notes=None,
    )

    assert summary.rows_imported == 3
    assert summary.duplicate_observations_coalesced == 2
    assert summary.remediation_findings_created == 1

    findings = db_session.query(Finding).all()
    assert len(findings) == 1
    instances = db_session.query(FindingInstance).all()
    assert len(instances) == 1
    assert instances[0].occurrence_count == 3


# --- (6): unknown achievement name remains a useful finding -----------------


def test_unknown_achievement_name_remains_useful_finding():
    data = {"achievements": [_achievement("Some Brand New Pentera Achievement Nobody Has Seen", 6.2)]}
    rows, _, _ = parse_json(_bytes(data))
    result = map_rows(rows)
    nf = result.findings[0]
    assert nf.normalized_type == "UNKNOWN"
    assert nf.category == "OTHER"
    # Title and severity are NOT destroyed by being unrecognized.
    assert nf.title == "Some Brand New Pentera Achievement Nobody Has Seen"
    assert nf.severity == "medium"  # 6.2 buckets to medium (4.0-6.9)
    assert nf.source_metadata["pentera_numeric_severity"] == 6.2


# --- (7): credential redaction still works recursively for parameters -------


def test_achievement_parameters_credential_redacted_recursively():
    data = {
        "achievements": [
            _achievement(
                "Leaked Credential",
                7.5,
                extra_parameters={"cracked_password": "Summer2024!", "nt_hash": "aad3b435b51404eeaad3b435b51404ee"},
            )
        ]
    }
    rows, _, _ = parse_json(_bytes(data))
    raw_parameters = rows[0].unmapped_fields.get("parameters", {})
    assert raw_parameters.get("cracked_password") == REDACTED_MARKER
    assert raw_parameters.get("nt_hash") == REDACTED_MARKER
    # Domain itself (not credential-shaped) survives untouched.
    assert raw_parameters.get("Domain") == "fabrikam.local"
    # Full raw copy is redacted too.
    assert "Summer2024!" not in json.dumps(rows[0].raw)


def test_achievement_summary_inline_secret_redacted():
    data = {
        "achievements": [
            _achievement(
                "Leaked Credential",
                7.5,
                summary=["Cracked password = Summer2024! found during assessment."],
            )
        ]
    }
    rows, _, _ = parse_json(_bytes(data))
    assert rows[0].description is not None
    assert "Summer2024!" not in rows[0].description
    assert "[REDACTED]" in rows[0].description


# --- (8): vulnerabilities remain available to the parser architecture -------


def test_vulnerabilities_only_export_still_imports_as_generic_findings():
    # No "achievements" collection at all -- vulnerabilities-only exports
    # (or any pre-existing generic JSON shape) must keep working exactly as
    # before this change, via the existing named-collection fallback.
    data = {"vulnerabilities": [{"finding": "ACL Abuse", "target": "WKS-1", "domain": "fabrikam.local"}]}
    rows, warnings, counts = parse_json(_bytes(data))
    assert len(rows) == 1
    assert rows[0].title == "ACL Abuse"
    assert counts["achievements_discovered"] == 0
    # Selected AS the findings source this time (achievements absent), so
    # it is not double-counted as a separate "discovered" vulnerabilities
    # collection -- it *is* the findings collection here.
    assert counts["vulnerabilities_discovered"] == 0


def test_achievements_discovered_zero_for_csv_import(db_session):
    # CSV imports never populate achievements/vulnerabilities counts.
    from app.services.import_service import import_pentera_csv
    import datetime

    csv_content = (
        b"Finding,Asset,Asset Type,Domain,Severity\n"
        b"Password Not Required,svc_backup,service_account,fabrikam.local,High\n"
    )
    summary = import_pentera_csv(
        db_session, csv_content, name="A1", assessment_date=datetime.date(2026, 8, 1),
        environment="fabrikam.local", source_filename="a.csv", notes=None,
    )
    assert summary.achievements_discovered == 0
    assert summary.vulnerabilities_discovered == 0
    assert summary.remediation_findings_created == 1


# --- (9): warning aggregation for many duplicate-cause achievements ---------


# ============================================================================
# Achievement identity / fingerprint collision-prevention tests
#
# A second real Pentera ADPA import (16k+ achievement objects across many
# distinct Achievement types) produced only 7 logical Findings in the
# tracker, most showing "Unknown Asset". Root cause: the fingerprint
# combined only normalized_type + domain + asset. When normalized_type was
# UNKNOWN (an unmapped achievement name -- the common case, since most real
# Achievement names don't match any TYPE_RULES keyword pattern) and asset
# fell back to a domain-level scope (no specific parameter identified an
# individual object), EVERY such achievement -- regardless of its actual
# name -- produced the exact same fingerprint and collapsed into one
# Finding. Fixed by folding a canonicalized source title into the
# fingerprint discriminator (see services/fingerprint.py,
# mapper.py's canonical_title). These tests prove the fix using only
# synthetic achievement names -- the real file was never requested or
# inspected, per explicit instruction.
# ============================================================================


def test_two_different_unknown_achievements_same_domain_no_asset_produce_two_findings(db_session):
    import datetime

    # Neither name matches any TYPE_RULES keyword pattern -- both stay
    # UNKNOWN, both have only a Domain parameter (no specific affected
    # object), so both fall back to the exact same (domain, domain)
    # asset/identifier pair. Before this fix, they collapsed into one
    # Finding purely because normalized_type/domain/asset all matched.
    data = {
        "achievements": [
            _achievement("Zebra Widget Nonstandard Check Alpha", 4.0, achievement_id="a1"),
            _achievement("Zebra Widget Nonstandard Check Beta", 4.0, achievement_id="a2"),
        ]
    }
    summary = import_pentera_json(
        db_session, _bytes(data), name="A1", assessment_date=datetime.date(2026, 8, 1),
        environment="fabrikam.local", source_filename="synthetic.json", notes=None,
    )
    assert summary.remediation_findings_created == 2
    findings = db_session.query(Finding).order_by(Finding.title).all()
    assert len(findings) == 2
    assert {f.title for f in findings} == {
        "Zebra Widget Nonstandard Check Alpha",
        "Zebra Widget Nonstandard Check Beta",
    }
    assert all(f.normalized_type == "UNKNOWN" for f in findings)
    assert all(f.asset.name == "fabrikam.local" for f in findings)


def test_same_achievement_name_repeated_239_times_is_one_finding(db_session):
    import datetime

    data = {
        "achievements": [
            _achievement("Using empty password(s)", 5.0, achievement_id=f"a{i}")
            for i in range(239)
        ]
    }
    summary = import_pentera_json(
        db_session, _bytes(data), name="A1", assessment_date=datetime.date(2026, 8, 1),
        environment="fabrikam.local", source_filename="synthetic.json", notes=None,
    )
    assert summary.remediation_findings_created == 1
    assert summary.duplicate_observations_coalesced == 238

    findings = db_session.query(Finding).all()
    assert len(findings) == 1
    instances = db_session.query(FindingInstance).all()
    assert len(instances) == 1
    assert instances[0].occurrence_count == 239


def test_same_achievement_name_distinct_assets_stay_separate(db_session):
    import datetime

    data = {
        "achievements": [
            _achievement("Password can be cracked using low GPU effort", 6.0, achievement_id="a1", extra_parameters={"Account": "userA"}),
            _achievement("Password can be cracked using low GPU effort", 6.0, achievement_id="a2", extra_parameters={"Account": "userB"}),
            _achievement("Password can be cracked using low GPU effort", 6.0, achievement_id="a3", extra_parameters={"Account": "userC"}),
        ]
    }
    summary = import_pentera_json(
        db_session, _bytes(data), name="A1", assessment_date=datetime.date(2026, 8, 1),
        environment="fabrikam.local", source_filename="synthetic.json", notes=None,
    )
    assert summary.remediation_findings_created == 3
    assert summary.duplicate_observations_coalesced == 0
    findings = db_session.query(Finding).all()
    assert len(findings) == 3
    assert {f.asset.name for f in findings} == {"userA", "userB", "userC"}
    assert all(f.title == "Password can be cracked using low GPU effort" for f in findings)
    assert all(f.occurrence_count == 1 for f in findings)


def test_different_password_cracking_achievement_names_remain_distinct(db_session):
    import datetime

    titles_and_severities = [
        ("Password can be cracked using low GPU effort", 3.0),
        ("Password can be cracked using high GPU effort", 6.0),
        ("Password can be cracked using a custom dictionary attack", 9.0),
    ]
    data = {
        "achievements": [
            _achievement(title, severity, achievement_id=f"a{i}")
            for i, (title, severity) in enumerate(titles_and_severities)
        ]
    }
    summary = import_pentera_json(
        db_session, _bytes(data), name="A1", assessment_date=datetime.date(2026, 8, 1),
        environment="fabrikam.local", source_filename="synthetic.json", notes=None,
    )
    # All three share normalized_type=WEAK_PASSWORD/category=CREDENTIAL_EXPOSURE
    # (same category is fine and expected) but must remain three distinct,
    # separately trackable Findings.
    assert summary.remediation_findings_created == 3
    findings = {f.title: f for f in db_session.query(Finding).all()}
    assert len(findings) == 3
    for title, severity in titles_and_severities:
        f = findings[title]
        assert f.normalized_type == "WEAK_PASSWORD"
        assert f.category == "CREDENTIAL_EXPOSURE"
        # (5) Numeric Pentera severity retained independently per finding,
        # not shared/overwritten across the three.
        assert f.pentera_numeric_severity == severity


def test_missing_asset_does_not_collide_unrelated_findings_at_scale(db_session):
    """(7) Generalizes the two-title case to 20 distinct unmapped
    achievement names, all domain-only (no specific affected object) --
    the exact shape of the real-world collapse-to-7 bug."""
    import datetime

    titles = [f"Zebra Widget Nonstandard Check {i:02d}" for i in range(20)]
    data = {"achievements": [_achievement(t, 5.0, achievement_id=f"a{i}") for i, t in enumerate(titles)]}
    summary = import_pentera_json(
        db_session, _bytes(data), name="A1", assessment_date=datetime.date(2026, 8, 1),
        environment="fabrikam.local", source_filename="synthetic.json", notes=None,
    )
    assert summary.remediation_findings_created == 20
    assert db_session.query(Finding).count() == 20


def test_cross_assessment_recurrence_still_works_with_title_based_fingerprint(db_session):
    """(6)/(8)/(9): parameters.Domain recognized, cross-assessment dedup
    still works, and recurrence across assessments A/B is tracked
    correctly -- the title-based fingerprint change must not break the
    existing recurring/resolved logic, only fix the collision bug."""
    import datetime

    date_a = datetime.date(2026, 8, 1)
    date_b = datetime.date(2026, 9, 1)

    payload_a = {
        "achievements": [
            _achievement("Password(s) stored in reversible encryption", 8.3, achievement_id=f"a{i}")
            for i in range(3)
        ]
    }
    summary_a = import_pentera_json(
        db_session, _bytes(payload_a), name="A1", assessment_date=date_a,
        environment="fabrikam.local", source_filename="a.json", notes=None,
    )
    assert summary_a.new_findings == 1
    assert summary_a.recurring_findings == 0

    finding = db_session.query(Finding).one()
    assert finding.asset.domain == "fabrikam.local"
    first_instance_count = finding.occurrence_count
    assert first_instance_count == 3

    # Second assessment: same logical achievement recurs, this time
    # observed 5 times -- must be recognized as the SAME Finding
    # (recurring, not new), with a SEPARATE FindingInstance for assessment
    # B carrying its own occurrence_count.
    payload_b = {
        "achievements": [
            _achievement("Password(s) stored in reversible encryption", 8.3, achievement_id=f"b{i}")
            for i in range(5)
        ]
    }
    summary_b = import_pentera_json(
        db_session, _bytes(payload_b), name="A2", assessment_date=date_b,
        environment="fabrikam.local", source_filename="b.json", notes=None,
    )
    assert summary_b.new_findings == 0
    assert summary_b.recurring_findings == 1
    assert db_session.query(Finding).count() == 1  # still the same one logical Finding

    db_session.refresh(finding)
    assert len(finding.instances) == 2
    # Latest instance (assessment B) reflects its own occurrence count;
    # assessment A's instance is untouched.
    assert finding.instances[0].occurrence_count == 3  # assessment A
    assert finding.instances[1].occurrence_count == 5  # assessment B
    assert finding.occurrence_count == 5  # Finding.occurrence_count == latest instance


def test_csv_two_different_findings_same_asset_remain_distinct(db_session):
    """(10) CSV regression: two different logical findings on the exact
    same asset/domain must remain distinct after the fingerprint change --
    unaffected by the achievement-specific work, but worth asserting
    directly since compute_fingerprint's call site changed for every
    import path, not just achievements."""
    import datetime

    from app.services.import_service import import_pentera_csv

    csv_content = (
        b"Finding,Severity,Target,Object Type,Domain\n"
        b"Password Not Required,High,svc_backup,service_account,fabrikam.local\n"
        b"Weak Password,Medium,svc_backup,service_account,fabrikam.local\n"
    )
    summary = import_pentera_csv(
        db_session, csv_content, name="A1", assessment_date=datetime.date(2026, 8, 1),
        environment="fabrikam.local", source_filename="a.csv", notes=None,
    )
    assert summary.new_findings == 2
    assert db_session.query(Finding).count() == 2


def test_at_least_15_distinct_real_achievement_names_produce_correct_finding_count(db_session):
    """Verification requirement: a synthetic Achievement set containing at
    least 15 distinct names (drawn from the real Pentera UI's visible
    Achievement type list, values/domain synthetic) with repeated
    occurrences must produce exactly that many logical Findings -- not
    collapse toward a small number the way the real second import did."""
    import datetime

    # title -> (repeat_count, expected_normalized_type)
    achievements_spec: dict[str, tuple[int, str]] = {
        "Using empty password(s)": (239, "EMPTY_PASSWORD"),
        "Password(s) stored in reversible encryption": (1, "REVERSIBLE_ENCRYPTION"),
        "Leaked cleartext password matches a known breach": (205, "LEAKED_CREDENTIAL"),
        # Matches LEAKED_CREDENTIAL (checked before WEAK_PASSWORD) because
        # it contains "leaked credential" -- a reasonable classification
        # given the phrasing; the point of this test is distinct-Finding
        # count and per-title occurrence_count, not the exact type chosen.
        "Password can be cracked leveraging leaked credentials": (2570, "LEAKED_CREDENTIAL"),
        "Leaked cleartext password closely matches account password": (12, "LEAKED_CREDENTIAL"),
        "Leaked username matches domain account naming convention": (45, "LEAKED_CREDENTIAL"),
        "Found users with Password-Not-Required flag set": (33, "PASSWORD_NOT_REQUIRED"),
        "Password can be cracked using low GPU effort": (88, "WEAK_PASSWORD"),
        "Password can be cracked using a custom dictionary attack": (19, "WEAK_PASSWORD"),
        "Found users with Password-Never-Expire flag set": (120, "PASSWORD_NEVER_EXPIRES"),
        "Found low complexity level password that not enough": (9, "PASSWORD_COMPLEXITY_WEAKNESS"),
        "Found password(s) with password(s) age greater than policy": (64, "PASSWORD_AGE_WEAKNESS"),
        "Found password(s) that do not adhere to the password policy": (3, "PASSWORD_POLICY_WEAKNESS"),
        "Password can be cracked using high GPU effort": (4578, "WEAK_PASSWORD"),
        "Found several non-admin users with identical passwords": (7, "PASSWORD_REUSE"),
        "Possibly too many domain administrators": (1, "DOMAIN_ADMIN_MEMBERSHIP"),
        "Password age permitted is too long": (15, "PASSWORD_AGE_WEAKNESS"),
        "Security Account Manager Remote Protocol exposure": (2, "SAMR_EXPOSURE"),
    }
    assert len(achievements_spec) >= 15

    achievement_objs = []
    counter = 0
    for title, (count, _expected_type) in achievements_spec.items():
        for _ in range(count):
            achievement_objs.append(_achievement(title, 6.0, achievement_id=f"a{counter}"))
            counter += 1

    data = {"achievements": achievement_objs}
    summary = import_pentera_json(
        db_session, _bytes(data), name="A1", assessment_date=datetime.date(2026, 8, 1),
        environment="fabrikam.local", source_filename="synthetic.json", notes=None,
    )

    assert summary.achievements_discovered == sum(c for c, _ in achievements_spec.values())
    assert summary.remediation_findings_created == len(achievements_spec)

    findings_by_title = {f.title: f for f in db_session.query(Finding).all()}
    assert len(findings_by_title) == len(achievements_spec)
    for title, (count, expected_type) in achievements_spec.items():
        f = findings_by_title[title]
        assert f.normalized_type == expected_type, f"{title!r} expected {expected_type}, got {f.normalized_type}"
        assert f.occurrence_count == count, f"{title!r} expected occurrence_count={count}, got {f.occurrence_count}"


def test_warning_aggregation_for_many_unknown_achievements(db_session):
    import datetime

    # "Zebra Widget Nonstandard Check" deliberately matches no TYPE_RULES
    # keyword pattern -- stays UNKNOWN so this test exercises warning
    # aggregation, not the (separately tested) mapping expansion.
    data = {
        "achievements": [
            _achievement("Zebra Widget Nonstandard Check Zeta-99", 5.0, achievement_id=f"a{i}", extra_parameters={"Account": f"user{i}"})
            for i in range(50)
        ]
    }
    summary = import_pentera_json(
        db_session, _bytes(data), name="A1", assessment_date=datetime.date(2026, 8, 1),
        environment="fabrikam.local", source_filename="synthetic.json", notes=None,
    )
    assert summary.unknown_mappings == 50
    # One aggregated warning, not fifty near-identical ones.
    matching = [w for w in summary.warnings if "Zebra Widget Nonstandard Check Zeta-99" in w and "imported as UNKNOWN" in w]
    assert len(matching) == 1
    assert "50 observation(s)" in matching[0]
    assert len(summary.warnings) < 10
