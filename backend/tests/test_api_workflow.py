import io


def _upload_csv(client, filename="test.csv", assessment_date="2026-05-01"):
    csv_content = (
        b"Finding,Severity,Target,Object Type,Domain,Exploitable\n"
        b"Domain Admin Membership,Critical,jsmith,user,corp.local,true\n"
    )
    return client.post(
        "/imports/pentera",
        data={"name": "Test Assessment", "assessment_date": assessment_date, "environment": "corp.local"},
        files={"file": (filename, io.BytesIO(csv_content), "text/csv")},
    )


def test_import_rejects_non_csv_file(client):
    resp = client.post(
        "/imports/pentera",
        data={"name": "Bad Upload", "assessment_date": "2026-05-01"},
        files={"file": ("evil.exe", io.BytesIO(b"not a csv"), "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_full_remediation_and_validation_workflow(client):
    resp = _upload_csv(client)
    assert resp.status_code == 200
    finding_id = client.get("/findings").json()[0]["id"]

    owner_resp = client.post("/owners", json={"name": "Identity Team", "team": "Identity"})
    assert owner_resp.status_code == 201
    owner_id = owner_resp.json()["id"]

    # Assign owner + move to IN_REMEDIATION
    patch_resp = client.patch(
        f"/findings/{finding_id}", json={"owner_id": owner_id, "status": "IN_REMEDIATION"}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "IN_REMEDIATION"
    assert patch_resp.json()["owner"]["id"] == owner_id

    # Cannot jump directly to VALIDATED
    blocked_resp = client.patch(f"/findings/{finding_id}", json={"status": "VALIDATED"})
    assert blocked_resp.status_code == 400

    # Add a remediation note, move to READY_FOR_VALIDATION
    remediation_resp = client.post(
        "/remediations",
        json={
            "finding_id": finding_id,
            "status": "READY_FOR_VALIDATION",
            "remediation_notes": "Removed from Domain Admins.",
        },
    )
    assert remediation_resp.status_code == 201
    assert remediation_resp.json()["status"] == "READY_FOR_VALIDATION"

    # Record a passing validation -> finding becomes VALIDATED
    validation_resp = client.post(
        "/validations",
        json={
            "finding_id": finding_id,
            "validation_method": "Manual AD query",
            "evidence": "Confirmed not in Domain Admins",
            "validation_date": "2026-05-10",
            "result": "PASS",
            "validated_by": "Analyst",
        },
    )
    assert validation_resp.status_code == 201

    final = client.get(f"/findings/{finding_id}").json()
    assert final["status"] == "VALIDATED"
    assert len(final["remediations"]) == 1
    assert len(final["validations"]) == 1


def test_failing_validation_reopens_to_in_remediation(client):
    _upload_csv(client)
    finding_id = client.get("/findings").json()[0]["id"]

    client.patch(f"/findings/{finding_id}", json={"status": "READY_FOR_VALIDATION"})
    resp = client.post(
        "/validations",
        json={
            "finding_id": finding_id,
            "validation_date": "2026-05-10",
            "result": "FAIL",
        },
    )
    assert resp.status_code == 201
    assert client.get(f"/findings/{finding_id}").json()["status"] == "IN_REMEDIATION"


def test_dashboard_reflects_second_assessment_comparison(client):
    _upload_csv(client, filename="a1.csv", assessment_date="2026-05-01")
    _upload_csv(client, filename="a2.csv", assessment_date="2026-06-01")

    dashboard = client.get("/dashboard").json()
    assert dashboard["assessment_count"] == 2
    assert dashboard["comparison"] is not None
    assert dashboard["comparison"]["recurring_findings"] == 1


def test_findings_search_and_filter(client):
    _upload_csv(client)
    resp = client.get("/findings", params={"priority": "P1"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.get("/findings", params={"priority": "P3"})
    assert resp.json() == []

    resp = client.get("/findings", params={"search": "jsmith"})
    assert len(resp.json()) == 1
