from app.services.risk_engine import compute_risk, score_priority


def test_base_severity_only():
    result = compute_risk(severity="low")
    assert result.score == 10
    assert result.priority == "P3"


def test_critical_tier0_privileged_credential_exposure_is_p1():
    result = compute_risk(
        severity="critical",
        tier_zero=True,
        privileged=True,
        credential_exposure=True,
        exploitable=True,
        asset_criticality="critical",
    )
    # 50 + 25 + 15 + 15 + 10 + 10 = 125, capped to 100
    assert result.score == 100
    assert result.priority == "P1"
    assert len(result.reasons) == 6


def test_score_is_capped_between_0_and_100():
    result = compute_risk(severity="critical", tier_zero=True, privileged=True,
                           credential_exposure=True, exploitable=True, asset_criticality="critical")
    assert 0 <= result.score <= 100


def test_priority_bands():
    assert score_priority(95) == "P1"
    assert score_priority(90) == "P1"
    assert score_priority(89) == "P2"
    assert score_priority(70) == "P2"
    assert score_priority(69) == "P3"
    assert score_priority(0) == "P3"


def test_reasons_are_human_readable_and_explain_score():
    result = compute_risk(severity="high", tier_zero=True)
    assert any("Base severity" in r for r in result.reasons)
    assert any("Tier 0" in r for r in result.reasons)
    assert len(result.reasons) == 2


def test_unknown_severity_defaults_to_medium_base():
    result = compute_risk(severity="not-a-real-severity")
    assert result.score == 20
