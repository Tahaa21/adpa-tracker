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


def test_warning_aggregation_for_many_unknown_achievements(db_session):
    import datetime

    data = {
        "achievements": [
            _achievement("Using empty password(s)", 5.0, achievement_id=f"a{i}", extra_parameters={"Account": f"user{i}"})
            for i in range(50)
        ]
    }
    summary = import_pentera_json(
        db_session, _bytes(data), name="A1", assessment_date=datetime.date(2026, 8, 1),
        environment="fabrikam.local", source_filename="synthetic.json", notes=None,
    )
    assert summary.unknown_mappings == 50
    # One aggregated warning, not fifty near-identical ones.
    matching = [w for w in summary.warnings if "Using empty password(s)" in w and "imported as UNKNOWN" in w]
    assert len(matching) == 1
    assert "50 observation(s)" in matching[0]
    assert len(summary.warnings) < 10
