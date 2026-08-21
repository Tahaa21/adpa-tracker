"""Simple, explainable risk engine.

Two separate, deliberately UN-merged outputs (see docs/DATA_MODEL.md and
docs/PENTERA_IMPORT.md "Achievement identity"/"Pentera severity bands" for
the full rationale — this file is the other half of that story):

- `Finding.severity` (low/medium/high/critical) — the bucketed **Pentera
  severity band**, computed once in mapper.py from either the numeric
  Pentera severity (see NUMERIC_SEVERITY_THRESHOLDS there) or a text
  severity label. This module treats it as authoritative INPUT, never
  recomputes it.
- `risk_score` (0-100) / `priority` (P1-P4) — the Tracker's OWN
  prioritization output, computed HERE, seeded from `Finding.severity` and
  then adjusted by contextual modifiers. Shown in the UI as "Tracker Risk
  Score" / "Tracker Priority", explicitly separate from "Pentera Severity"
  / "Pentera Severity Rating" — never merged into one unexplained number.

    risk_score = baseline floor for the severity band
                 + tier_zero + privileged + credential_exposure
                 + exploitable + asset_criticality   (capped to [0, 100])

    priority:
      1. BASE priority comes from the severity band ALONE, before any
         contextual modifier: CRITICAL->P1, HIGH->P2, MEDIUM->P3, LOW->P4.
      2. Tier 0 / Domain Controller relevance (DCSync, Domain Admin /
         Enterprise Admin exposure — anything with tier_zero=True) is an
         UNCONDITIONAL OVERRIDE straight to P1, regardless of the base
         priority. These conditions are inherently top-priority for AD
         security regardless of how Pentera itself scored that one
         achievement (e.g. a Domain Admin Membership finding Pentera rated
         only medium-severity is still a P1 for us).
      3. Any OTHER single contextual factor (privileged group membership,
         leaked/cleartext credential exposure, a confirmed exploitable
         condition, or a highly critical affected asset) promotes priority
         by exactly ONE level (P4->P3->P2->P1), applied AT MOST ONCE even
         if several such factors are present together. This keeps P1
         meaningful — several real risk factors stacking up shows up in
         `risk_score` (which DOES add per-factor), not by racing every
         multi-factor finding to P1.
      4. Promotion is monotonic toward P1 only. A CRITICAL Pentera
         severity finding starts at P1 and nothing here can move it lower.
"""
from dataclasses import dataclass, field

# Baseline (floor, ceiling) risk_score range per Pentera severity band —
# these ARE the "suggested baseline ranges" contract: a finding's
# risk_score always starts at the floor of its band and modifiers only
# push it upward from there (capped at 100), so a CRITICAL Pentera
# severity finding can never end up with a bizarrely low Tracker Risk
# Score (e.g. severity 8.6 producing a risk_score of 35 — see
# docs/PENTERA_IMPORT.md for the exact anti-pattern this baseline exists
# to prevent).
BASE_SCORE_RANGE: dict[str, tuple[int, int]] = {
    "critical": (80, 100),
    "high": (60, 79),
    "medium": (30, 59),
    "low": (10, 29),
}

# Base priority from severity band alone, before any contextual promotion.
BASE_PRIORITY: dict[str, str] = {
    "critical": "P1",
    "high": "P2",
    "medium": "P3",
    "low": "P4",
}

# Ascending importance — index 0 is least urgent. Promotion always moves
# toward the end of this list, never backward.
PRIORITY_LEVELS = ["P4", "P3", "P2", "P1"]

TIER_ZERO_MODIFIER = 8
PRIVILEGED_MODIFIER = 4
CREDENTIAL_EXPOSURE_MODIFIER = 6
EXPLOITABLE_MODIFIER = 6
ASSET_CRITICALITY_MODIFIER = 4


@dataclass
class RiskResult:
    score: int
    priority: str
    reasons: list[str] = field(default_factory=list)


def _promote_priority(priority: str, levels: int) -> str:
    idx = min(PRIORITY_LEVELS.index(priority) + levels, len(PRIORITY_LEVELS) - 1)
    return PRIORITY_LEVELS[idx]


def compute_risk(
    severity: str,
    tier_zero: bool = False,
    privileged: bool = False,
    credential_exposure: bool = False,
    exploitable: bool = False,
    asset_criticality: str = "medium",
) -> RiskResult:
    severity = (severity or "medium").lower()
    if severity not in BASE_SCORE_RANGE:
        severity = "medium"

    base_floor, _base_ceiling = BASE_SCORE_RANGE[severity]
    base_priority = BASE_PRIORITY[severity]

    reasons = [f"{severity.capitalize()} Pentera severity (base {base_floor})"]
    score = base_floor

    secondary_triggered = False

    if tier_zero:
        score += TIER_ZERO_MODIFIER
        reasons.append(f"Tier 0 / Domain Controller relevance (+{TIER_ZERO_MODIFIER})")
    if privileged:
        score += PRIVILEGED_MODIFIER
        reasons.append(f"Privileged access impact (+{PRIVILEGED_MODIFIER})")
        secondary_triggered = True
    if credential_exposure:
        score += CREDENTIAL_EXPOSURE_MODIFIER
        reasons.append(f"Leaked/cleartext credential exposure (+{CREDENTIAL_EXPOSURE_MODIFIER})")
        secondary_triggered = True
    if exploitable:
        score += EXPLOITABLE_MODIFIER
        reasons.append(f"Confirmed exploitable by assessment (+{EXPLOITABLE_MODIFIER})")
        secondary_triggered = True
    if (asset_criticality or "medium").lower() in ("high", "critical"):
        score += ASSET_CRITICALITY_MODIFIER
        reasons.append(
            f"Affected asset criticality: {asset_criticality.capitalize()} (+{ASSET_CRITICALITY_MODIFIER})"
        )
        secondary_triggered = True

    score = max(0, min(100, score))

    if tier_zero:
        priority = "P1"
        if base_priority != "P1":
            reasons.append(
                f"Priority promoted to P1: Tier 0 / Domain Controller relevance overrides base {base_priority}"
            )
    elif secondary_triggered:
        priority = _promote_priority(base_priority, 1)
        if priority != base_priority:
            reasons.append(f"Priority promoted from {base_priority} to {priority}: contextual risk factor(s) present")
    else:
        priority = base_priority

    return RiskResult(score=score, priority=priority, reasons=reasons)
