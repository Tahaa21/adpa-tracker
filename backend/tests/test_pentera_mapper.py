from app.integrations.pentera.mapper import classify, map_rows
from app.integrations.pentera.schemas import RawPenteraRow


def _row(**kwargs) -> RawPenteraRow:
    defaults = dict(row_number=2, title="Password Not Required", asset_name="svc_backup")
    defaults.update(kwargs)
    return RawPenteraRow(**defaults)


def test_classify_known_types():
    assert classify("Password Not Required")[0] == "PASSWORD_NOT_REQUIRED"
    assert classify("Domain Admin Membership")[0] == "DOMAIN_ADMIN_MEMBERSHIP"
    assert classify("DCSync Exposure detected")[0] == "DCSYNC_EXPOSURE"
    assert classify("Kerberos Delegation misconfiguration")[0] == "DELEGATION_RISK"


def test_classify_unknown_defaults_to_unknown_other():
    normalized_type, category = classify("Some Brand New Pentera Check")
    assert normalized_type == "UNKNOWN"
    assert category == "OTHER"


def test_unknown_finding_still_imports_with_original_title_preserved():
    result = map_rows([_row(title="Something Pentera Invented Yesterday")])
    assert result.rows_skipped == 0
    assert len(result.findings) == 1
    nf = result.findings[0]
    assert nf.normalized_type == "UNKNOWN"
    assert nf.category == "OTHER"
    assert nf.source_metadata["source_title"] == "Something Pentera Invented Yesterday"
    # Warnings are aggregated per distinct cause, not one per row (see
    # docs/PENTERA_IMPORT.md "Warning aggregation") -- still contains the
    # original title and a stable "imported as UNKNOWN" marker.
    assert any("Something Pentera Invented Yesterday" in w and "imported as UNKNOWN" in w for w in result.warnings)


def test_row_missing_title_and_asset_is_skipped_not_crashed():
    result = map_rows([_row(title=None, asset_name=None)])
    assert result.rows_skipped == 1
    assert len(result.findings) == 0
    assert any("skipped" in w for w in result.warnings)


def test_severity_normalization():
    result = map_rows([_row(severity="Severe")])
    assert result.findings[0].severity == "critical"

    result = map_rows([_row(severity="informational")])
    assert result.findings[0].severity == "low"

    result = map_rows([_row(severity=None)])
    assert result.findings[0].severity == "medium"


def test_domain_admin_membership_flags_tier_zero_and_privileged():
    result = map_rows([_row(title="Domain Admin Membership")])
    nf = result.findings[0]
    assert nf.tier_zero is True
    assert nf.privileged is True


def test_exploitable_flag_parsed_from_truthy_strings():
    result = map_rows([_row(exploitable="Yes")])
    assert result.findings[0].exploitable is True

    result = map_rows([_row(exploitable="No")])
    assert result.findings[0].exploitable is False
