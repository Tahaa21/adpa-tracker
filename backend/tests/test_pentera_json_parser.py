import json

import pytest

from app.integrations.pentera import mapper
from app.integrations.pentera.json_parser import parse_json
from app.integrations.pentera.parser import ParseError
from app.services.redaction import REDACTED_MARKER


def _bytes(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


# --- top-level array -------------------------------------------------------


def test_top_level_array_of_findings():
    data = [
        {"finding": "Password Not Required", "target": "svc_backup", "objectType": "service_account", "domain": "corp.local"},
        {"finding": "Domain Admin Membership", "target": "jsmith", "objectType": "user", "domain": "corp.local"},
    ]
    rows, warnings = parse_json(_bytes(data))
    assert len(rows) == 2
    assert rows[0].title == "Password Not Required"
    assert rows[0].asset_name == "svc_backup"
    assert rows[0].asset_type == "service_account"
    assert rows[0].domain == "corp.local"
    assert rows[0].row_number == 1
    assert rows[1].row_number == 2
    assert any("Findings collection identified" in w for w in warnings)


# --- nested findings array ---------------------------------------------------


def test_nested_findings_array_under_known_key():
    data = {
        "assessment_name": "Q3 Assessment",
        "generated_at": "2026-07-15",
        "findings": [
            {"title": "Weak Password", "asset": "administrator", "assetType": "user", "domain": "fabrikam.local"},
        ],
    }
    rows, warnings = parse_json(_bytes(data))
    assert len(rows) == 1
    assert rows[0].title == "Weak Password"
    assert rows[0].asset_name == "administrator"
    assert any("findings" in w for w in warnings)
    # No "no standard findings key" warning since 'findings' IS a standard key.
    assert not any("No standard findings key" in w for w in warnings)


def test_nested_findings_array_under_results_key_deeper():
    data = {
        "meta": {"tool": "Pentera"},
        "report": {"results": [{"finding": "Trust Risk", "target": "partner.local", "domain": "fabrikam.local"}]},
    }
    rows, warnings = parse_json(_bytes(data))
    assert len(rows) == 1
    assert rows[0].title == "Trust Risk"


# --- nested asset sub-object -------------------------------------------------


def test_nested_asset_object_preferred_over_top_level():
    data = [
        {
            "finding": "Delegation Risk",
            "asset": {"name": "SQL01", "type": "computer", "domain": "fabrikam.local"},
            "severity": "High",
        }
    ]
    rows, _ = parse_json(_bytes(data))
    assert rows[0].asset_name == "SQL01"
    assert rows[0].asset_type == "computer"
    assert rows[0].domain == "fabrikam.local"


# --- unknown / undetected structure -----------------------------------------


def test_unknown_nested_structure_falls_back_to_largest_array_with_warning():
    data = {
        "weirdWrapperKey": {
            "somethingElse": [
                {"vulnerability": "ACL Abuse", "host": "WKS-1", "domain": "fabrikam.local"},
                {"vulnerability": "ACL Abuse", "host": "WKS-2", "domain": "fabrikam.local"},
            ]
        }
    }
    rows, warnings = parse_json(_bytes(data))
    assert len(rows) == 2
    assert any("No standard findings key" in w for w in warnings)


def test_unrecognizable_structure_raises_parse_error():
    data = {"foo": "bar", "baz": 123}
    with pytest.raises(ParseError):
        parse_json(_bytes(data))


def test_does_not_silently_drop_a_sibling_collection():
    data = {
        "findings": [{"finding": f"Finding {i}", "target": f"host{i}", "domain": "fabrikam.local"} for i in range(10)],
        "assets_inventory": [{"name": f"host{i}", "type": "computer"} for i in range(10)],
    }
    rows, warnings = parse_json(_bytes(data))
    assert len(rows) == 10
    assert any("assets_inventory" in w and "NOT treated as findings" in w for w in warnings)


# --- missing fields ----------------------------------------------------------


def test_finding_missing_title_and_asset_is_still_parsed_row_but_mapper_skips_later():
    # json_parser itself never drops a row; missing-both-fields skipping is
    # mapper.py's job (shared with CSV) — verify the row still comes through
    # with None values so mapper can apply its existing skip logic.
    data = [{"severity": "High"}]
    rows, _ = parse_json(_bytes(data))
    assert len(rows) == 1
    assert rows[0].title is None
    assert rows[0].asset_name is None


def test_finding_missing_asset_type_defaults_handled_by_mapper():
    data = [{"finding": "Service Account Risk", "target": "svc_x", "domain": "fabrikam.local"}]
    rows, _ = parse_json(_bytes(data))
    assert rows[0].asset_type is None  # mapper.py normalizes this to "unknown"


# --- credential-shaped keys (recursive redaction) ---------------------------


def test_credential_shaped_keys_redacted_recursively():
    data = [
        {
            "finding": "Weak Password",
            "target": "administrator",
            "domain": "fabrikam.local",
            "evidence": {
                "cracked_password": "Summer2024!",
                "nt_hash": "aad3b435b51404eeaad3b435b51404ee",
                "lm_hash": "aad3b435b51404ee",
            },
            "credentials": {"username": "administrator", "password": "Summer2024!"},
        }
    ]
    rows, _ = parse_json(_bytes(data))
    raw = rows[0].raw
    assert raw["evidence"] == REDACTED_MARKER
    assert raw["credentials"] == REDACTED_MARKER
    # Functional fields untouched.
    assert rows[0].asset_name == "administrator"


def test_credential_shaped_key_at_top_level_scalar():
    data = [{"finding": "Leaked Credential", "target": "svc_vpn", "domain": "fabrikam.local", "ntlm": "deadbeefdeadbeefdeadbeefdeadbeef"}]
    rows, _ = parse_json(_bytes(data))
    assert rows[0].raw["ntlm"] == REDACTED_MARKER
    assert rows[0].unmapped_fields.get("ntlm") == REDACTED_MARKER


# --- inline secrets in free text --------------------------------------------


def test_inline_secret_in_description_redacted_in_raw_copy():
    # RawPenteraRow.description itself is intentionally left unredacted at
    # parse time (functional field, matches CSV behavior exactly) — the
    # archival `raw` copy is redacted immediately, and the FUNCTIONAL field
    # is redacted one layer later by mapper.map_rows() (verified below).
    data = [
        {
            "finding": "Weak Password",
            "target": "svc_test",
            "domain": "fabrikam.local",
            "description": "Cracked password = Summer2024! during assessment.",
        }
    ]
    rows, _ = parse_json(_bytes(data))
    assert "Summer2024!" not in json.dumps(rows[0].raw)
    assert "[REDACTED]" in rows[0].raw["description"]


def test_inline_secret_in_description_redacted_after_mapping():
    data = [
        {
            "finding": "Weak Password",
            "target": "svc_test",
            "domain": "fabrikam.local",
            "description": "Cracked password = Summer2024! during assessment.",
            "recommendation": "Rotate credential: Summer2024! immediately.",
        }
    ]
    rows, _ = parse_json(_bytes(data))
    result = mapper.map_rows(rows)
    nf = result.findings[0]
    assert "Summer2024!" not in (nf.description or "")
    assert "Summer2024!" not in (nf.remediation_guidance or "")
    assert "[REDACTED]" in (nf.description or "")
    assert "[REDACTED]" in (nf.remediation_guidance or "")


def test_inline_secret_in_generic_unmapped_field_redacted():
    data = [
        {
            "finding": "Weak Password",
            "target": "svc_test",
            "domain": "fabrikam.local",
            "notes": "Found password: Summer2024! in a script.",
        }
    ]
    rows, _ = parse_json(_bytes(data))
    assert "Summer2024!" not in json.dumps(rows[0].raw)
    assert "Summer2024!" not in json.dumps(rows[0].unmapped_fields)


# --- malformed / empty JSON --------------------------------------------------


def test_malformed_json_raises_parse_error():
    with pytest.raises(ParseError):
        parse_json(b"{not valid json,,,")


def test_empty_array_raises_parse_error():
    with pytest.raises(ParseError):
        parse_json(b"[]")


def test_empty_object_raises_parse_error():
    with pytest.raises(ParseError):
        parse_json(b"{}")


def test_top_level_scalar_raises_parse_error():
    with pytest.raises(ParseError):
        parse_json(b'"just a string"')


def test_top_level_array_of_non_objects_raises_parse_error():
    with pytest.raises(ParseError):
        parse_json(b"[1, 2, 3]")


# --- unmapped field preservation ---------------------------------------------


def test_unmapped_fields_preserved():
    data = [
        {
            "finding": "Password Reuse",
            "target": "nkim",
            "domain": "fabrikam.local",
            "pentera_internal_id": "ABC-123",
        }
    ]
    rows, _ = parse_json(_bytes(data))
    assert rows[0].unmapped_fields.get("pentera_internal_id") == "ABC-123"
