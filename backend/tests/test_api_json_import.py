import io
import json


def _upload_json(client, filename="test.json", assessment_date="2026-05-01"):
    payload = {
        "findings": [
            {"finding": "Domain Admin Membership", "severity": "Critical", "target": "jsmith", "objectType": "user", "domain": "corp.local", "exploitable": True},
        ]
    }
    content = json.dumps(payload).encode("utf-8")
    return client.post(
        "/imports/pentera",
        data={"name": "Test JSON Assessment", "assessment_date": assessment_date, "environment": "corp.local"},
        files={"file": (filename, io.BytesIO(content), "application/json")},
    )


def test_json_upload_through_api_end_to_end(client):
    resp = _upload_json(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_imported"] == 1
    assert body["new_findings"] == 1

    finding = client.get("/findings").json()[0]
    assert finding["normalized_type"] == "DOMAIN_ADMIN_MEMBERSHIP"
    assert finding["asset"]["external_identifier"].lower() == "jsmith"


def test_csv_upload_still_works_through_same_endpoint(client):
    """Regression: the same /imports/pentera endpoint must still accept CSV
    after adding JSON support, and dispatch to the CSV parser correctly."""
    csv_content = (
        b"Finding,Severity,Target,Object Type,Domain,Exploitable\n"
        b"Domain Admin Membership,Critical,jsmith,user,corp.local,true\n"
    )
    resp = client.post(
        "/imports/pentera",
        data={"name": "Test CSV Assessment", "assessment_date": "2026-05-01", "environment": "corp.local"},
        files={"file": ("test.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert resp.status_code == 200
    assert resp.json()["rows_imported"] == 1


def test_upload_rejects_unsupported_extension(client):
    resp = client.post(
        "/imports/pentera",
        data={"name": "Bad Upload", "assessment_date": "2026-05-01"},
        files={"file": ("report.pdf", io.BytesIO(b"%PDF-1.4 not really a pdf"), "application/pdf")},
    )
    assert resp.status_code == 400
    assert "json" in resp.json()["detail"].lower() or "csv" in resp.json()["detail"].lower()


def test_malformed_json_upload_returns_422(client):
    resp = client.post(
        "/imports/pentera",
        data={"name": "Bad JSON", "assessment_date": "2026-05-01"},
        files={"file": ("bad.json", io.BytesIO(b"{not valid json"), "application/json")},
    )
    assert resp.status_code == 422
