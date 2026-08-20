from app.integrations.pentera.mapper import map_rows
from app.integrations.pentera.parser import parse_csv
from app.integrations.pentera.schemas import RawPenteraRow
from app.services.redaction import (
    REDACTED_MARKER,
    is_sensitive_header,
    redact_inline_credentials,
    redact_row,
)


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


def test_redact_row_scans_non_sensitive_columns_for_inline_credentials():
    """A column whose HEADER isn't flagged (e.g. a generic 'Notes' column)
    can still leak a secret in its VALUE — must be caught by pass 2."""
    row = {"Notes": "Found password: Summer2024! in a script.", "Target": "jdoe"}
    redacted = redact_row(row)
    assert "Summer2024!" not in redacted["Notes"]
    assert "[REDACTED]" in redacted["Notes"]
    assert redacted["Target"] == "jdoe"


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


def test_redact_inline_credentials_catches_key_value_pairs():
    text = "Account svc_backup password = Summer2024! was found in a config file."
    redacted = redact_inline_credentials(text)
    assert "Summer2024!" not in redacted
    assert "[REDACTED]" in redacted
    assert "svc_backup" in redacted  # non-secret context preserved


def test_redact_inline_credentials_handles_colon_form_and_hash():
    text = "NTLM hash: aad3b435b51404eeaad3b435b51404ee for user jdoe."
    redacted = redact_inline_credentials(text)
    assert "aad3b435b51404eeaad3b435b51404ee" not in redacted
    assert "jdoe" in redacted


def test_redact_inline_credentials_leaves_ordinary_guidance_alone():
    text = "Remove standing Domain Admins membership; reset the password regularly."
    redacted = redact_inline_credentials(text)
    assert redacted == text  # no key:value pair present, nothing to redact


def test_redact_inline_credentials_handles_none_and_empty():
    assert redact_inline_credentials(None) is None
    assert redact_inline_credentials("") == ""


def test_mapper_redacts_inline_credentials_in_description_and_recommendation():
    row = RawPenteraRow(
        row_number=2,
        title="Weak Password",
        asset_name="jdoe",
        description="Cracked password = Summer2024! during assessment.",
        recommendation="Rotate credential: Summer2024! immediately.",
    )
    result = map_rows([row])
    nf = result.findings[0]
    assert "Summer2024!" not in (nf.description or "")
    assert "Summer2024!" not in (nf.remediation_guidance or "")
    assert "[REDACTED]" in (nf.description or "")
    assert "[REDACTED]" in (nf.remediation_guidance or "")
