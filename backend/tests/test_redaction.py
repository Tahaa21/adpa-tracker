from app.integrations.pentera.parser import parse_csv
from app.services.redaction import REDACTED_MARKER, is_sensitive_header, redact_row


def test_is_sensitive_header_matches_common_credential_column_names():
    for header in [
        "Password",
        "Cracked Password",
        "Password Hash",
        "NTLM Hash",
        "Credential",
        "Secret",
        "Evidence",
        "API Key",
        "Cleartext Password",
    ]:
        assert is_sensitive_header(header), f"expected {header!r} to be flagged sensitive"


def test_is_sensitive_header_does_not_flag_ordinary_columns():
    for header in ["Finding", "Severity", "Target", "Domain", "Description", "SAM Account Name"]:
        assert not is_sensitive_header(header), f"did not expect {header!r} to be flagged sensitive"


def test_redact_row_replaces_only_sensitive_values():
    row = {"Finding": "Weak Password", "Target": "jdoe", "Cracked Password": "Summer2024!"}
    redacted = redact_row(row)
    assert redacted["Finding"] == "Weak Password"
    assert redacted["Target"] == "jdoe"
    assert redacted["Cracked Password"] == REDACTED_MARKER


def test_redact_row_leaves_empty_values_alone():
    row = {"Password": ""}
    redacted = redact_row(row)
    assert redacted["Password"] == ""


def test_parser_redacts_credential_columns_in_raw_and_unmapped_storage():
    csv_bytes = (
        b"Finding,Target,Cracked Password\n"
        b"Weak Password,jdoe,Summer2024!\n"
    )
    rows, _ = parse_csv(csv_bytes)
    row = rows[0]
    # Functional fields stay real.
    assert row.title == "Weak Password"
    assert row.asset_name == "jdoe"
    # Archival copies are redacted.
    assert row.raw["Cracked Password"] == REDACTED_MARKER
    assert row.unmapped_fields["Cracked Password"] == REDACTED_MARKER
    # Non-sensitive raw values are preserved verbatim.
    assert row.raw["Target"] == "jdoe"
