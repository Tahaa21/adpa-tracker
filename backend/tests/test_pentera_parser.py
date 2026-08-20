import pytest

from app.integrations.pentera.parser import ParseError, parse_csv


def test_parses_known_headers():
    csv_bytes = (
        b"Finding,Severity,Target,Object Type,Domain\n"
        b"Password Not Required,High,svc_backup,service_account,corp.local\n"
    )
    rows, warnings = parse_csv(csv_bytes)
    assert len(rows) == 1
    assert rows[0].title == "Password Not Required"
    assert rows[0].severity == "High"
    assert rows[0].asset_name == "svc_backup"
    assert warnings == []


def test_tolerates_alternate_header_names():
    """Different Pentera export using different column names for the same fields."""
    csv_bytes = (
        b"Vulnerability,Risk Severity,Affected Asset,Entity Type,Environment\n"
        b"Weak Password,Critical,administrator,user,fabrikam.local\n"
    )
    rows, _ = parse_csv(csv_bytes)
    assert len(rows) == 1
    assert rows[0].title == "Weak Password"
    assert rows[0].asset_name == "administrator"
    assert rows[0].domain == "fabrikam.local"


def test_preserves_unmapped_columns_in_metadata():
    csv_bytes = (
        b"Finding,Target,Custom Pentera Field\n"
        b"Password Reuse,jdoe,some-extra-value\n"
    )
    rows, _ = parse_csv(csv_bytes)
    assert rows[0].unmapped_fields.get("Custom Pentera Field") == "some-extra-value"


def test_missing_recognizable_columns_raises_parse_error():
    csv_bytes = b"Random Column A,Random Column B\nfoo,bar\n"
    with pytest.raises(ParseError):
        parse_csv(csv_bytes)


def test_empty_header_raises_parse_error():
    with pytest.raises(ParseError):
        parse_csv(b"")


def test_row_numbers_start_after_header():
    csv_bytes = (
        b"Finding,Target\n"
        b"Password Reuse,jdoe\n"
        b"Weak Password,asmith\n"
    )
    rows, _ = parse_csv(csv_bytes)
    assert [r.row_number for r in rows] == [2, 3]
