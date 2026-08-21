from app.services.risk_engine import BASE_PRIORITY, BASE_SCORE_RANGE, compute_risk


def test_base_severity_only_low():
    result = compute_risk(severity="low")
    assert result.score == 10
    assert result.priority == "P4"
    assert len(result.reasons) == 1


def test_base_severity_only_medium():
    result = compute_risk(severity="medium")
    assert result.score == 30
    assert result.priority == "P3"


def test_base_severity_only_high():
    result = compute_risk(severity="high")
    assert result.score == 60
    assert result.priority == "P2"


def test_base_severity_only_critical():
    result = compute_risk(severity="critical")
    assert result.score == 80
    assert result.priority == "P1"


def test_score_is_capped_between_0_and_100():
    result = compute_risk(
        severity="critical", tier_zero=True, privileged=True,
        credential_exposure=True, exploitable=True, asset_criticality="critical",
    )
    assert 0 <= result.score <= 100
    assert result.score == 100  # 80 + 8 + 4 + 6 + 6 + 4 = 108, capped


def test_unknown_severity_defaults_to_medium_base():
    result = compute_risk(severity="not-a-real-severity")
    assert result.score == 30
    assert result.priority == "P3"


def test_tier_zero_overrides_to_p1_even_from_low_base():
    result = compute_risk(severity="low", tier_zero=True)
    assert result.priority == "P1"
    assert any("Tier 0" in r for r in result.reasons)
    assert any("promoted to P1" in r for r in result.reasons)


def test_secondary_factor_promotes_exactly_one_level():
    result = compute_risk(severity="medium", privileged=True)
    assert result.priority == "P2"  # P3 -> P2, not P1


def test_multiple_secondary_factors_promote_only_one_level_not_stacked():
    """Do not over-promote everything to P1: several non-tier-zero
    contextual factors together still only move priority by one level,
    even though each adds its own points to risk_score."""
    result = compute_risk(
        severity="medium", privileged=True, credential_exposure=True,
        exploitable=True, asset_criticality="critical",
    )
    assert result.priority == "P2"  # still just one level up from P3
    assert result.score > BASE_SCORE_RANGE["medium"][0]  # but score reflects all four factors


def test_critical_severity_with_no_modifiers_stays_p1():
    result = compute_risk(severity="critical")
    assert result.priority == "P1"


def test_critical_severity_cannot_be_demoted_by_absence_of_modifiers():
    # No modifier can ever lower priority below the severity band's base --
    # there is no "demotion" path in this engine at all.
    result = compute_risk(severity="critical", tier_zero=False, privileged=False)
    assert result.priority == "P1"


def test_reasons_are_human_readable_and_explain_score():
    result = compute_risk(severity="high", tier_zero=True)
    assert any("Pentera severity" in r for r in result.reasons)
    assert any("Tier 0" in r for r in result.reasons)


# --- Explicit boundary tests: numeric Pentera severity -> band -> base priority ---
# (severity bucket -> BASE_PRIORITY only; no contextual modifiers applied)


def test_boundary_1_0_is_low_p4():
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    bucket = _bucket_numeric_severity(1.0)
    assert bucket == "low"
    assert BASE_PRIORITY[bucket] == "P4"
    assert compute_risk(severity=bucket).priority == "P4"


def test_boundary_1_9_is_low_p4():
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    bucket = _bucket_numeric_severity(1.9)
    assert bucket == "low"
    assert compute_risk(severity=bucket).priority == "P4"


def test_boundary_2_0_is_medium_p3():
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    bucket = _bucket_numeric_severity(2.0)
    assert bucket == "medium"
    assert compute_risk(severity=bucket).priority == "P3"


def test_boundary_4_9_is_medium_p3():
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    bucket = _bucket_numeric_severity(4.9)
    assert bucket == "medium"
    assert compute_risk(severity=bucket).priority == "P3"


def test_boundary_5_0_is_high_p2():
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    bucket = _bucket_numeric_severity(5.0)
    assert bucket == "high"
    assert compute_risk(severity=bucket).priority == "P2"


def test_boundary_6_9_is_high_p2():
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    bucket = _bucket_numeric_severity(6.9)
    assert bucket == "high"
    assert compute_risk(severity=bucket).priority == "P2"


def test_boundary_7_0_is_critical_p1():
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    bucket = _bucket_numeric_severity(7.0)
    assert bucket == "critical"
    assert compute_risk(severity=bucket).priority == "P1"


def test_boundary_8_6_is_critical_p1():
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    bucket = _bucket_numeric_severity(8.6)
    assert bucket == "critical"
    assert compute_risk(severity=bucket).priority == "P1"


def test_no_overlapping_boundary_conditions():
    """Every value in [0, 10] maps to exactly one band -- no gaps, no
    double-matches at the boundaries themselves."""
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    samples = [round(x * 0.1, 1) for x in range(0, 101)]  # 0.0 .. 10.0
    for value in samples:
        bucket = _bucket_numeric_severity(value)
        assert bucket in ("low", "medium", "high", "critical")


# --- Contextual promotion scenarios given explicitly in the task ------------


def test_severity_6_0_plus_tier0_promotes_to_p1():
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    bucket = _bucket_numeric_severity(6.0)
    assert bucket == "high"
    result = compute_risk(severity=bucket, tier_zero=True)
    assert result.priority == "P1"


def test_severity_5_5_plus_dcsync_promotes_to_p1():
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    bucket = _bucket_numeric_severity(5.5)
    assert bucket == "high"
    # DCSync is represented as tier_zero=True (see mapper.py TYPE_FLAGS
    # DCSYNC_EXPOSURE -> tier_zero=True).
    result = compute_risk(severity=bucket, tier_zero=True)
    assert result.priority == "P1"


def test_severity_4_0_plus_privileged_may_promote_one_level():
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    bucket = _bucket_numeric_severity(4.0)
    assert bucket == "medium"
    base_result = compute_risk(severity=bucket)
    assert base_result.priority == "P3"
    promoted_result = compute_risk(severity=bucket, privileged=True)
    # Documented rule: a single non-tier-zero contextual factor promotes
    # exactly one level -- P3 -> P2, not all the way to P1.
    assert promoted_result.priority == "P2"


def test_severity_8_6_without_modifiers_remains_p1():
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    bucket = _bucket_numeric_severity(8.6)
    result = compute_risk(severity=bucket)
    assert result.priority == "P1"


def test_meaningful_separation_across_all_four_priorities():
    """The result should produce meaningful separation across P1/P2/P3/P4,
    not collapse everything toward P1."""
    from app.integrations.pentera.mapper import _bucket_numeric_severity

    priorities = {
        compute_risk(severity=_bucket_numeric_severity(1.0)).priority,
        compute_risk(severity=_bucket_numeric_severity(3.0)).priority,
        compute_risk(severity=_bucket_numeric_severity(6.0)).priority,
        compute_risk(severity=_bucket_numeric_severity(8.0)).priority,
    }
    assert priorities == {"P4", "P3", "P2", "P1"}


def test_not_everything_gets_promoted_to_p1():
    """A low-severity finding with no qualifying context stays P4 -- the
    engine must not systematically over-promote."""
    result = compute_risk(severity="low")
    assert result.priority == "P4"
    result2 = compute_risk(severity="low", asset_criticality="low")
    assert result2.priority == "P4"
