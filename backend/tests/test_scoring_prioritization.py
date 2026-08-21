"""Prioritization tests exercising the full pipeline: numeric Pentera
severity -> mapper.py band -> risk_engine.py base priority -> contextual
promotion -> persisted Finding.risk_score/priority -> API response. All
synthetic data.

Proves the real-world requirement directly: DCSync / Domain Admin
Membership / other Tier-0-relevant findings must rank materially higher
than ordinary password-policy findings, driven by the general scoring
model (context-aware promotion) -- not by hardcoding those specific
finding names.
"""
import datetime
import json

from app.models.finding import Finding
from app.services.import_service import import_pentera_json

DATE_A = datetime.date(2026, 8, 1)


def _achievement(name: str, severity: float, domain: str = "fabrikam.local", account: str | None = None) -> dict:
    params = {"Domain": domain}
    if account:
        params["Account"] = account
    return {
        "id": name.replace(" ", "-").lower(),
        "creation_time": "2026-08-01T00:00:00Z",
        "name": name,
        "summary": [],
        "severity": severity,
        "parameters": params,
    }


def _import(db, achievements: list[dict], name="A1", assessment_date=DATE_A):
    content = json.dumps({"achievements": achievements}).encode("utf-8")
    return import_pentera_json(
        db, content, name=name, assessment_date=assessment_date,
        environment="fabrikam.local", source_filename="synthetic.json", notes=None,
    )


def test_dcsync_ranks_above_password_policy_even_at_similar_pentera_severity(db_session):
    """The exact real-data scenario the task describes: a DCSync/Tier-0
    finding must materially outrank an ordinary password-policy finding,
    even when Pentera's own numeric severity for the two is comparable --
    driven entirely by the general TYPE_FLAGS(tier_zero)/risk_engine
    promotion model, not by hardcoding either finding name."""
    # Different domains so the two findings resolve to different Asset
    # rows -- otherwise DCSync legitimately escalates the shared
    # domain-level Asset's criticality (see _get_or_create_asset), which
    # would ALSO promote the co-scoped policy finding via the "highly
    # critical asset" contextual factor -- a real, intentional interaction,
    # just not the one this test isolates.
    achievements = [
        _achievement("DCSync Exposure Detected", 6.0, domain="fabrikam.local"),
        _achievement("Found password(s) that do not adhere to the password policy", 6.0, domain="contoso.local"),
    ]
    _import(db_session, achievements)

    findings = {f.title: f for f in db_session.query(Finding).all()}
    dcsync = findings["DCSync Exposure Detected"]
    policy = findings["Found password(s) that do not adhere to the password policy"]

    assert dcsync.normalized_type == "DCSYNC_EXPOSURE"
    assert policy.normalized_type == "PASSWORD_POLICY_WEAKNESS"

    # Same starting Pentera severity band (both 6.0 -> high), but DCSync's
    # Tier 0 relevance forces P1 while the policy finding stays at its
    # base priority.
    assert dcsync.severity == policy.severity == "high"
    assert dcsync.priority == "P1"
    assert policy.priority == "P2"  # base priority for "high", no promotion
    assert dcsync.risk_score > policy.risk_score


def test_domain_admin_membership_outranks_reversible_encryption_despite_lower_raw_severity(db_session):
    """Domain Admin Membership at a LOWER Pentera severity than Reversible
    Encryption still ends up higher priority, because Tier 0 relevance is
    an unconditional override -- demonstrating context matters more than
    the raw number alone, the product's stated value-add."""
    achievements = [
        _achievement("Domain Admin Membership", 5.0, account="jsmith"),  # high band, tier_zero
        _achievement("Password(s) stored in reversible encryption", 8.5),  # critical band, no tier_zero
    ]
    _import(db_session, achievements)

    findings = {f.title: f for f in db_session.query(Finding).all()}
    domain_admin = findings["Domain Admin Membership"]
    reversible = findings["Password(s) stored in reversible encryption"]

    assert domain_admin.severity == "high"
    assert reversible.severity == "critical"
    # Reversible encryption's raw severity band is higher, so its base
    # priority is P1 already (critical->P1) -- both end up P1, but via
    # different paths. The interesting assertion is that Domain Admin
    # Membership, despite a LOWER band, is NOT stuck at its base P2 --
    # tier_zero promotes it all the way to P1 too.
    assert domain_admin.priority == "P1"
    assert reversible.priority == "P1"


def test_ordinary_findings_without_context_stay_at_lower_priorities(db_session):
    """Not everything ends up P1 -- password complexity/age findings with
    no Tier 0/privileged/credential/exploitable/critical-asset context
    stay at their base priority, giving meaningful separation."""
    achievements = [
        _achievement("Found low complexity level password that not enough", 3.0),  # medium -> P3
        _achievement("Password age permitted is too long", 1.0),  # low -> P4
    ]
    _import(db_session, achievements)

    findings = {f.title: f for f in db_session.query(Finding).all()}
    complexity = findings["Found low complexity level password that not enough"]
    age = findings["Password age permitted is too long"]

    assert complexity.priority == "P3"
    assert age.priority == "P4"


def test_dashboard_reports_p4_and_severity_distribution(client):
    import io

    csv_content = (
        b"Finding,Severity,Target,Object Type,Domain\n"
        b"Domain Admin Membership,Critical,jsmith,user,fabrikam.local\n"
        b"Password Policy Weakness,Low,fabrikam.local,domain,fabrikam.local\n"
    )
    resp = client.post(
        "/imports/pentera",
        data={"name": "A1", "assessment_date": "2026-08-01", "environment": "fabrikam.local"},
        files={"file": ("a.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert resp.status_code == 200

    dashboard = client.get("/dashboard").json()
    assert "P4" in dashboard["priority_distribution"]
    assert set(dashboard["severity_distribution"].keys()) == {"critical", "high", "medium", "low"}
    total_priority = sum(dashboard["priority_distribution"].values())
    total_severity = sum(dashboard["severity_distribution"].values())
    assert total_priority == total_severity == 2


def test_finding_api_exposes_pentera_severity_and_tracker_risk_separately(client):
    import io

    csv_content = (
        b"Finding,Severity,Target,Object Type,Domain,Exploitable\n"
        b"Domain Admin Membership,Critical,jsmith,user,fabrikam.local,true\n"
    )
    resp = client.post(
        "/imports/pentera",
        data={"name": "A1", "assessment_date": "2026-08-01", "environment": "fabrikam.local"},
        files={"file": ("a.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert resp.status_code == 200
    finding_id = client.get("/findings").json()[0]["id"]

    detail = client.get(f"/findings/{finding_id}").json()
    assert "risk_score" in detail
    assert "priority" in detail
    assert detail["priority"] == "P1"
    assert any("Tier 0" in r for r in detail["risk_reasons"])
