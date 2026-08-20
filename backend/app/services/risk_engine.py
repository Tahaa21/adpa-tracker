"""Simple, explainable risk engine.

Deliberately a small set of additive rules rather than a statistical model —
every point on the score can be traced back to a plain-English reason. See
docs/DATA_MODEL.md and the product brief for the rationale.

    risk_score (0-100) = base_severity + tier0 + privileged + credential_exposure
                          + exploitable + asset_criticality   (capped to [0, 100])

    priority: 90-100 = P1, 70-89 = P2, 0-69 = P3
"""
from dataclasses import dataclass, field

BASE_SEVERITY_SCORE = {
    "critical": 50,
    "high": 35,
    "medium": 20,
    "low": 10,
}

TIER_ZERO_MODIFIER = 25
PRIVILEGED_MODIFIER = 15
CREDENTIAL_EXPOSURE_MODIFIER = 15
EXPLOITABLE_MODIFIER = 10
ASSET_CRITICALITY_MODIFIER = 10

P1_THRESHOLD = 90
P2_THRESHOLD = 70


@dataclass
class RiskResult:
    score: int
    priority: str
    reasons: list[str] = field(default_factory=list)


def score_priority(score: int) -> str:
    if score >= P1_THRESHOLD:
        return "P1"
    if score >= P2_THRESHOLD:
        return "P2"
    return "P3"


def compute_risk(
    severity: str,
    tier_zero: bool = False,
    privileged: bool = False,
    credential_exposure: bool = False,
    exploitable: bool = False,
    asset_criticality: str = "medium",
) -> RiskResult:
    severity = (severity or "medium").lower()
    base = BASE_SEVERITY_SCORE.get(severity, BASE_SEVERITY_SCORE["medium"])
    reasons = [f"Base severity: {severity.capitalize()} (+{base})"]
    total = base

    if tier_zero:
        total += TIER_ZERO_MODIFIER
        reasons.append(f"Tier 0 object or capability (+{TIER_ZERO_MODIFIER})")
    if privileged:
        total += PRIVILEGED_MODIFIER
        reasons.append(f"Privileged account/group involved (+{PRIVILEGED_MODIFIER})")
    if credential_exposure:
        total += CREDENTIAL_EXPOSURE_MODIFIER
        reasons.append(f"Credential exposure risk (+{CREDENTIAL_EXPOSURE_MODIFIER})")
    if exploitable:
        total += EXPLOITABLE_MODIFIER
        reasons.append(f"Confirmed exploitable by assessment (+{EXPLOITABLE_MODIFIER})")
    if (asset_criticality or "medium").lower() in ("high", "critical"):
        total += ASSET_CRITICALITY_MODIFIER
        reasons.append(
            f"Affected asset criticality: {asset_criticality.capitalize()} (+{ASSET_CRITICALITY_MODIFIER})"
        )

    total = max(0, min(100, total))
    return RiskResult(score=total, priority=score_priority(total), reasons=reasons)
