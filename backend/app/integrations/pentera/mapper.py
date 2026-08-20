"""Maps tolerant-parsed Pentera rows into NormalizedFinding objects.

Keyword-based classification into normalized_type/category. Adding a new
Pentera finding phrasing is a one-line addition to TYPE_RULES — no structural
change needed. Unrecognized findings are never a hard failure: they import as
normalized_type=UNKNOWN, category=OTHER, with the original title preserved.
"""
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


def _normalize_severity(raw: str | None) -> str:
    if not raw:
        return "medium"
    return SEVERITY_ALIASES.get(raw.strip().lower(), "medium")


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
    result = ParseResult(rows_processed=len(rows))

    for row in rows:
        if not row.title and not row.asset_name:
            result.warnings.append(f"Row {row.row_number}: missing both title and asset, skipped.")
            result.rows_skipped += 1
            continue

        title = (row.title or "Unnamed Pentera Finding").strip()
        if not row.title:
            result.warnings.append(
                f"Row {row.row_number}: missing finding title, used placeholder title."
            )

        normalized_type, category = classify(title)
        if normalized_type == "UNKNOWN":
            result.warnings.append(
                f"Row {row.row_number}: unrecognized finding type '{title}', imported as UNKNOWN."
            )

        asset_name = (row.asset_name or "Unknown Asset").strip()
        if not row.asset_name:
            result.warnings.append(f"Row {row.row_number}: missing asset name, used placeholder.")

        asset_type = _normalize_asset_type(row.asset_type)
        if row.asset_type and asset_type == "unknown":
            result.warnings.append(
                f"Row {row.row_number}: unrecognized asset type '{row.asset_type}', defaulted to 'unknown'."
            )

        severity = _normalize_severity(row.severity)
        domain = (row.domain or "").strip().lower()
        identifier = (row.identifier or asset_name).strip()

        privileged, tier_zero, credential_exposure = TYPE_FLAGS.get(
            normalized_type, (False, False, False)
        )
        exploitable = bool(row.exploitable and row.exploitable.strip().lower() in TRUTHY)

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
                source_metadata={
                    "source_title": title,
                    "unmapped_fields": row.unmapped_fields,
                },
                raw_row=row.raw,
            )
        )

    return result
