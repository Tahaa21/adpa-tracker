"""Maps tolerant-parsed Pentera rows into NormalizedFinding objects.

Keyword-based classification into normalized_type/category. Adding a new
Pentera finding phrasing is a one-line addition to TYPE_RULES — no structural
change needed. Unrecognized findings are never a hard failure: they import as
normalized_type=UNKNOWN, category=OTHER, with the original title AND
severity preserved (an unfamiliar name is never a reason to lose useful
remediation-tracking data).
"""
from collections import Counter

from app.integrations.pentera.schemas import NormalizedFinding, ParseResult, RawPenteraRow
from app.services.redaction import redact_inline_credentials

# Ordered (normalized_type, category, [required keyword groups]) — first match wins.
# Each keyword group is a list of alternative substrings; ALL groups must match
# (i.e. groups are AND'd, alternatives within a group are OR'd).
TYPE_RULES: list[tuple[str, str, list[list[str]]]] = [
    ("DCSYNC_EXPOSURE", "TIER_0", [["dcsync", "dc sync"]]),
    ("DOMAIN_ADMIN_MEMBERSHIP", "TIER_0", [["domain admin"]]),
    ("PASSWORD_NOT_REQUIRED", "ACCOUNT_HYGIENE", [["password"], ["not required", "not_required"]]),
    ("PASSWORD_NEVER_EXPIRES", "ACCOUNT_HYGIENE", [["password"], ["never expires", "does not expire"]]),
    ("REVERSIBLE_ENCRYPTION", "CREDENTIAL_EXPOSURE", [["reversible encryption"]]),
    ("PASSWORD_REUSE", "CREDENTIAL_EXPOSURE", [["password reuse", "reused password", "password is reused"]]),
    ("LEAKED_CREDENTIAL", "CREDENTIAL_EXPOSURE", [["leaked credential", "breached password", "leaked password"]]),
    ("WEAK_PASSWORD", "CREDENTIAL_EXPOSURE", [["weak password", "cracked password", "password cracked"]]),
    ("DORMANT_PRIVILEGED_ACCOUNT", "PRIVILEGE", [["dormant", "inactive", "stale"], ["privileged", "admin"]]),
    ("DELEGATION_RISK", "DELEGATION", [["delegation"]]),
    ("ACL_ABUSE", "PRIVILEGE", [["acl", "dacl"], ["abuse", "misconfigur", "weak"]]),
    ("PASSWORD_POLICY_WEAKNESS", "POLICY_CONFIGURATION", [["password policy"]]),
    ("PRIVILEGED_GROUP_MEMBERSHIP", "PRIVILEGE", [["privileged group", "admin group"]]),
    ("SERVICE_ACCOUNT_RISK", "PRIVILEGE", [["service account"]]),
    ("TRUST_RISK", "TRUST", [["trust"]]),
]

SEVERITY_ALIASES = {
    "critical": "critical",
    "severe": "critical",
    "high": "high",
    "medium": "medium",
    "moderate": "medium",
    "low": "low",
    "informational": "low",
    "info": "low",
}

# Deterministic mapping from a NUMERIC Pentera severity (e.g. an achievement's
# `severity: 8.3`) to our internal low/medium/high/critical bucket.
#
# This is NOT a claim that Pentera's numeric scale is CVSS — we have no
# Pentera documentation or code evidence confirming that, and the task that
# introduced this deliberately said not to assume it. These thresholds
# simply reuse the same numeric band boundaries CVSS v3.x happens to use
# (0.1-3.9 Low / 4.0-6.9 Medium / 7.0-8.9 High / 9.0-10.0 Critical) because,
# absent better information, they're a well-known, reasonable default for a
# 0-10 severity scale. If Pentera's real scale/documentation turns out to
# differ, adjust NUMERIC_SEVERITY_THRESHOLDS — nothing else needs to change.
# The original numeric value is never discarded: see
# NormalizedFinding.source_metadata["pentera_numeric_severity"] below.
NUMERIC_SEVERITY_THRESHOLDS: list[tuple[float, str]] = [
    (9.0, "critical"),
    (7.0, "high"),
    (4.0, "medium"),
    (0.0, "low"),
]

ASSET_TYPE_ALIASES = {
    "user": "user",
    "account": "user",
    "group": "group",
    "computer": "computer",
    "host": "computer",
    "server": "computer",
    "workstation": "computer",
    "domain": "domain",
    "policy": "policy",
    "gpo": "policy",
    "service_account": "service_account",
    "service account": "service_account",
}

TRUTHY = {"true", "yes", "1", "y", "confirmed", "verified"}

# normalized_type -> (privileged, tier_zero, credential_exposure)
TYPE_FLAGS: dict[str, tuple[bool, bool, bool]] = {
    "DCSYNC_EXPOSURE": (True, True, True),
    "DOMAIN_ADMIN_MEMBERSHIP": (True, True, False),
    "PRIVILEGED_GROUP_MEMBERSHIP": (True, False, False),
    "DORMANT_PRIVILEGED_ACCOUNT": (True, False, False),
    "PASSWORD_REUSE": (False, False, True),
    "LEAKED_CREDENTIAL": (False, False, True),
    "WEAK_PASSWORD": (False, False, True),
    "REVERSIBLE_ENCRYPTION": (False, False, True),
    "PASSWORD_NOT_REQUIRED": (False, False, True),
    "ACL_ABUSE": (True, False, False),
    "SERVICE_ACCOUNT_RISK": (False, False, False),
    "DELEGATION_RISK": (True, False, False),
    "TRUST_RISK": (False, False, False),
}


def _bucket_numeric_severity(value: float) -> str:
    for threshold, bucket in NUMERIC_SEVERITY_THRESHOLDS:
        if value >= threshold:
            return bucket
    return "low"


def _parse_numeric_severity(raw: str) -> float | None:
    try:
        return float(raw)
    except ValueError:
        return None


def _normalize_severity(raw: str | None) -> str:
    if not raw:
        return "medium"
    raw = raw.strip()
    numeric = _parse_numeric_severity(raw)
    if numeric is not None:
        return _bucket_numeric_severity(numeric)
    return SEVERITY_ALIASES.get(raw.lower(), "medium")


def _normalize_asset_type(raw: str | None) -> str:
    if not raw:
        return "unknown"
    return ASSET_TYPE_ALIASES.get(raw.strip().lower(), "unknown")


def classify(title: str) -> tuple[str, str]:
    """Return (normalized_type, category) for a raw finding title."""
    lowered = title.lower()
    for normalized_type, category, groups in TYPE_RULES:
        if all(any(kw in lowered for kw in group) for group in groups):
            return normalized_type, category
    return "UNKNOWN", "OTHER"


def map_rows(rows: list[RawPenteraRow]) -> ParseResult:
    """Maps rows to normalized findings.

    Per-row structural issues (unrecognized finding type, missing
    title/asset, unrecognized asset type) are AGGREGATED into one summary
    warning per distinct cause rather than one warning per row — a real
    Pentera export can have thousands of rows sharing the same
    unrecognized-name cause (e.g. "Using empty password(s)"), and one
    warning per row would flood the UI/API response. See
    docs/PENTERA_IMPORT.md "Warning aggregation".
    """
    result = ParseResult(rows_processed=len(rows))

    missing_both_count = 0
    missing_title_count = 0
    missing_asset_count = 0
    unrecognized_asset_type_counts: Counter[str] = Counter()
    unknown_type_counts: Counter[str] = Counter()

    for row in rows:
        if not row.title and not row.asset_name:
            missing_both_count += 1
            result.rows_skipped += 1
            continue

        title = (row.title or "Unnamed Pentera Finding").strip()
        if not row.title:
            missing_title_count += 1

        normalized_type, category = classify(title)
        if normalized_type == "UNKNOWN":
            unknown_type_counts[title] += 1

        asset_name = (row.asset_name or "Unknown Asset").strip()
        if not row.asset_name:
            missing_asset_count += 1

        asset_type = _normalize_asset_type(row.asset_type)
        if row.asset_type and asset_type == "unknown":
            unrecognized_asset_type_counts[row.asset_type] += 1

        severity = _normalize_severity(row.severity)
        domain = (row.domain or "").strip().lower()
        identifier = (row.identifier or asset_name).strip()

        privileged, tier_zero, credential_exposure = TYPE_FLAGS.get(
            normalized_type, (False, False, False)
        )
        exploitable = bool(row.exploitable and row.exploitable.strip().lower() in TRUTHY)

        source_metadata = {
            "source_title": title,
            "unmapped_fields": row.unmapped_fields,
        }
        numeric_severity = _parse_numeric_severity(row.severity) if row.severity else None
        if numeric_severity is not None:
            # Preserve the original Pentera numeric severity (e.g. 8.3)
            # alongside the bucketed low/medium/high/critical value used
            # everywhere else — never discarded.
            source_metadata["pentera_numeric_severity"] = numeric_severity

        result.findings.append(
            NormalizedFinding(
                row_number=row.row_number,
                normalized_type=normalized_type,
                category=row.category or category,
                title=title if normalized_type != "UNKNOWN" else title,
                source_title=title,
                severity=severity,
                # Redact any "key: value" / "key=value" credential pattern
                # embedded in free text (defense in depth beyond the
                # header-based column redaction in parser.py — see
                # services/redaction.py for scope/limits).
                description=redact_inline_credentials(row.description),
                remediation_guidance=redact_inline_credentials(row.recommendation),
                asset_name=asset_name,
                asset_type=asset_type,
                asset_external_identifier=identifier,
                domain=domain,
                exploitable=exploitable,
                privileged=privileged,
                tier_zero=tier_zero,
                credential_exposure=credential_exposure,
                source_metadata=source_metadata,
                raw_row=row.raw,
            )
        )

    if missing_both_count:
        result.warnings.append(
            f"{missing_both_count} row(s) skipped: missing both title and asset."
        )
    if missing_title_count:
        result.warnings.append(
            f"{missing_title_count} row(s) missing a finding title; used a placeholder title."
        )
    if missing_asset_count:
        result.warnings.append(
            f"{missing_asset_count} row(s) missing an asset name; used a placeholder."
        )
    for asset_type_raw, count in unrecognized_asset_type_counts.most_common():
        result.warnings.append(
            f"{count} row(s) had unrecognized asset type '{asset_type_raw}', defaulted to 'unknown'."
        )
    for title, count in unknown_type_counts.most_common():
        result.warnings.append(f"{title}: {count} observation(s) imported as UNKNOWN.")

    return result
