#!/usr/bin/env python3
"""Generates the sanitized sample Pentera-style CSV/JSON files in sample-data/.

All names/hosts/domains below are fictional (fabrikam.local, a Microsoft
sample domain long used in docs/training material). No real company,
customer, or credential data. Re-run this script to regenerate the files
deterministically.

Assessment 1 and Assessment 2 (CSV) intentionally use different column
headers (see HEADERS_A / HEADERS_B) to demonstrate the tolerant Pentera CSV
parser. Assessment 3 (JSON) continues the same fabrikam.local story one
step further, in a genuinely JSON-shaped structure (nested `asset` objects,
not flattened columns) to demonstrate the JSON parser specifically — see
docs/PENTERA_IMPORT.md's disclaimer: this is a structurally representative
sanitized sample, not a copy of a real Pentera JSON export (we don't have
one to copy from).

Assessment 2 resolves several of the highest-risk findings from Assessment 1
and adds a handful of new lower-severity findings; Assessment 3 resolves a
few more and adds a couple more — so all three together demonstrate
measurable risk reduction over time, across both supported formats sharing
the same fingerprint space (re-importing the same asset/finding in a
different format is still recognized as the same logical issue).
"""
import csv
import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "sample-data"

DOMAIN = "fabrikam.local"

# (title, severity, asset_name, asset_type, description, recommendation, exploitable)
FINDINGS = [
    ("Domain Admin Membership", "Critical", "jsmith", "user",
     "User account is a direct member of the Domain Admins group.",
     "Remove standing Domain Admins membership; use just-in-time privileged access instead.", True),
    ("Domain Admin Membership", "Critical", "agarcia", "user",
     "User account is a direct member of the Domain Admins group.",
     "Remove standing Domain Admins membership; use just-in-time privileged access instead.", False),
    ("DCSync Exposure", "Critical", "svc_reporting", "service_account",
     "Account holds Replicating Directory Changes rights, enabling DCSync.",
     "Remove replication rights from the account; audit who granted them.", True),
    ("DCSync Exposure", "High", "svc_sync", "service_account",
     "Account holds Replicating Directory Changes rights, enabling DCSync.",
     "Remove replication rights from the account; audit who granted them.", False),
    ("Privileged Group Membership", "High", "mchen", "user",
     "User account is a member of the Backup Operators group.",
     "Review necessity of Backup Operators membership; remove if not required.", False),
    ("Privileged Group Membership", "High", "tward", "user",
     "User account is a member of the Account Operators group.",
     "Review necessity of Account Operators membership; remove if not required.", False),
    ("Privileged Group Membership", "Medium", "efoster", "user",
     "User account is a member of the Server Operators group.",
     "Review necessity of Server Operators membership; remove if not required.", False),
    ("Privileged Group Membership", "Low", "hpatel", "user",
     "User account is a member of the Print Operators group.",
     "Review necessity of Print Operators membership; remove if not required.", False),
    ("Dormant Privileged Account", "High", "old_admin", "user",
     "Privileged account has not authenticated in over 180 days.",
     "Disable or remove the dormant privileged account.", False),
    ("Dormant Privileged Account", "Medium", "temp_admin2", "user",
     "Privileged account has not authenticated in over 180 days.",
     "Disable or remove the dormant privileged account.", False),
    ("Dormant Privileged Account", "Medium", "svc_old_backup", "service_account",
     "Privileged service account has not authenticated in over 180 days.",
     "Disable or remove the dormant privileged account.", False),
    ("Dormant Privileged Account", "High", "jold_admin", "user",
     "Privileged account has not authenticated in over 180 days.",
     "Disable or remove the dormant privileged account.", False),
    ("ACL Abuse", "High", "WKS-207", "computer",
     "Weak DACL grants GenericAll to a low-privileged group on this object.",
     "Remove the excessive ACE and audit who added it.", True),
    ("ACL Abuse", "Medium", "Default Domain Policy", "policy",
     "Weak DACL allows unauthorized GPO edits.",
     "Restrict GPO edit rights to Domain Admins / delegated GPO admins only.", False),
    ("Delegation Risk", "High", "SQL01", "computer",
     "Computer object is trusted for unconstrained delegation.",
     "Convert to constrained delegation or remove delegation entirely.", False),
    ("Delegation Risk", "Medium", "APP03", "computer",
     "Computer object is trusted for unconstrained delegation.",
     "Convert to constrained delegation or remove delegation entirely.", False),
    ("Delegation Risk", "Low", "FS02", "computer",
     "Computer object has broad constrained delegation rights.",
     "Narrow the constrained delegation target list.", False),
    ("Password Not Required", "High", "svc_backup", "service_account",
     "PASSWD_NOTREQD flag is set on the account.",
     "Clear the PASSWD_NOTREQD flag and set a strong password.", False),
    ("Password Not Required", "Medium", "svc_ftp", "service_account",
     "PASSWD_NOTREQD flag is set on the account.",
     "Clear the PASSWD_NOTREQD flag and set a strong password.", False),
    ("Password Not Required", "High", "guest_acct", "user",
     "PASSWD_NOTREQD flag is set on the account.",
     "Clear the PASSWD_NOTREQD flag and set a strong password.", False),
    ("Password Not Required", "Medium", "svc_legacy2", "service_account",
     "PASSWD_NOTREQD flag is set on the account.",
     "Clear the PASSWD_NOTREQD flag and set a strong password.", False),
    ("Password Never Expires", "Medium", "svc_sql", "service_account",
     "Account password is configured to never expire.",
     "Enable password expiration or move to a managed service account (gMSA).", False),
    ("Password Never Expires", "Medium", "svc_web01", "service_account",
     "Account password is configured to never expire.",
     "Enable password expiration or move to a managed service account (gMSA).", False),
    ("Password Never Expires", "Low", "kwilliams", "user",
     "Account password is configured to never expire.",
     "Enable standard password expiration policy for this account.", False),
    ("Password Never Expires", "Low", "svc_print", "service_account",
     "Account password is configured to never expire.",
     "Enable password expiration or move to a managed service account (gMSA).", False),
    ("Reversible Encryption", "High", "svc_legacy", "service_account",
     "Account is configured to store passwords using reversible encryption.",
     "Disable the reversible encryption flag on this account.", False),
    ("Password Reuse", "Medium", "dthompson", "user",
     "Password matches a password used elsewhere in the assessed environment.",
     "Force a password reset and enforce unique passwords.", False),
    ("Password Reuse", "Medium", "rlee", "user",
     "Password matches a password used elsewhere in the assessed environment.",
     "Force a password reset and enforce unique passwords.", False),
    ("Password Reuse", "Low", "nkim", "user",
     "Password matches a password used elsewhere in the assessed environment.",
     "Force a password reset and enforce unique passwords.", False),
    ("Leaked Credential", "High", "bnguyen", "user",
     "Password matches a value found in a known public breach corpus.",
     "Force an immediate password reset and enable breached-password protection.", True),
    ("Leaked Credential", "Critical", "svc_vpn", "service_account",
     "Password matches a value found in a known public breach corpus.",
     "Force an immediate password reset and enable breached-password protection.", True),
    ("Weak Password", "High", "svc_test", "service_account",
     "Password was cracked by the assessment engine in under one hour.",
     "Rotate the password and enforce a stronger password policy.", True),
    ("Weak Password", "Medium", "jbrown", "user",
     "Password was cracked by the assessment engine in under one hour.",
     "Rotate the password and enforce a stronger password policy.", True),
    ("Weak Password", "Medium", "svc_monitor", "service_account",
     "Password was cracked by the assessment engine in under one hour.",
     "Rotate the password and enforce a stronger password policy.", False),
    ("Weak Password", "Low", "svc_archive", "service_account",
     "Password was cracked by the assessment engine in under one hour.",
     "Rotate the password and enforce a stronger password policy.", False),
    ("Weak Password", "Critical", "administrator", "user",
     "Built-in Administrator password was cracked by the assessment engine.",
     "Rotate the password immediately and enable LAPS for local admin accounts.", True),
    ("Password Policy Weakness", "Medium", "fabrikam.local", "domain",
     "Default domain password policy allows short, non-complex passwords.",
     "Raise minimum length and enable complexity requirements domain-wide.", False),
    ("Password Policy Weakness", "Low", "Contractors PSO", "policy",
     "Fine-grained password policy for contractors is weaker than default.",
     "Align the fine-grained policy with the domain baseline.", False),
    ("Service Account Risk", "Medium", "svc_backup", "service_account",
     "Service account has interactive logon rights it does not require.",
     "Remove interactive logon rights; restrict to service logon only.", False),
    ("Service Account Risk", "High", "svc_deploy", "service_account",
     "Service account has excessive rights across multiple servers.",
     "Scope the account's rights to only the systems it needs.", False),
    ("Service Account Risk", "Medium", "svc_scanner", "service_account",
     "Service account credentials are shared across multiple scheduled tasks.",
     "Issue dedicated credentials per task; avoid credential sharing.", False),
    ("Service Account Risk", "Low", "svc_helpdesk", "service_account",
     "Service account has more file share access than its function requires.",
     "Right-size file share ACLs for this account.", False),
    ("Trust Risk", "Medium", "partner.local", "domain",
     "External trust to partner.local is configured without SID filtering.",
     "Enable SID filtering / quarantine on the external trust.", False),
    ("Trust Risk", "Low", "vendor.local", "domain",
     "Forest trust to vendor.local allows broader authentication scope than required.",
     "Scope authentication on the trust to only the required resources.", False),
    ("Anonymous LDAP Bind Enabled", "Medium", "DC01", "computer",
     "Domain controller allows anonymous LDAP binds.",
     "Disable anonymous LDAP binds via dsHeuristics.", False),
    ("Anonymous LDAP Bind Enabled", "Medium", "DC02", "computer",
     "Domain controller allows anonymous LDAP binds.",
     "Disable anonymous LDAP binds via dsHeuristics.", False),
    ("SMB Signing Not Required", "Low", "WKS-118", "computer",
     "SMB signing is not enforced, enabling relay attacks.",
     "Enforce SMB signing via Group Policy.", False),
    ("Null Session Enabled", "Low", "FS01", "computer",
     "Null sessions are permitted, allowing anonymous enumeration.",
     "Restrict anonymous access via RestrictAnonymous registry policy.", False),
]

# Findings resolved between Assessment 1 and Assessment 2 (fixed / no longer
# observed) — deliberately the highest-risk ones, to show real risk reduction.
RESOLVED_TITLES_ASSETS = {
    ("Domain Admin Membership", "jsmith"),
    ("DCSync Exposure", "svc_reporting"),
    ("ACL Abuse", "WKS-207"),
    ("Password Not Required", "guest_acct"),
    ("Leaked Credential", "bnguyen"),
    ("Leaked Credential", "svc_vpn"),
    ("Weak Password", "administrator"),
    ("Delegation Risk", "SQL01"),
    ("Weak Password", "svc_test"),
    ("Dormant Privileged Account", "old_admin"),
}

# New findings first observed in Assessment 2 — mostly lower severity.
NEW_IN_ASSESSMENT_2 = [
    ("Password Never Expires", "Low", "svc_newapp", "service_account",
     "Account password is configured to never expire.",
     "Enable password expiration or move to a managed service account (gMSA).", False),
    ("Weak Password", "Medium", "efoster", "user",
     "Password was cracked by the assessment engine in under one hour.",
     "Rotate the password and enforce a stronger password policy.", False),
    ("Privileged Group Membership", "Medium", "jcarter", "user",
     "User account is a member of the Backup Operators group.",
     "Review necessity of Backup Operators membership; remove if not required.", False),
    ("Service Account Risk", "Low", "svc_reporting2", "service_account",
     "Service account has more file share access than its function requires.",
     "Right-size file share ACLs for this account.", False),
    ("Anonymous LDAP Bind Enabled", "Low", "DC03", "computer",
     "Domain controller allows anonymous LDAP binds.",
     "Disable anonymous LDAP binds via dsHeuristics.", False),
]

# Findings resolved between Assessment 2 and Assessment 3 (JSON) — a few
# more of the remaining higher-severity items get fixed.
RESOLVED_TITLES_ASSETS_3 = {
    ("DCSync Exposure", "svc_sync"),
    ("Domain Admin Membership", "agarcia"),
    ("Reversible Encryption", "svc_legacy"),
}

# New findings first observed in Assessment 3 (JSON-only).
NEW_IN_ASSESSMENT_3 = [
    ("Password Reuse", "Low", "ghall", "user",
     "Password matches a password used elsewhere in the assessed environment.",
     "Force a password reset and enforce unique passwords.", False),
    ("SMB Signing Not Required", "Low", "WKS-231", "computer",
     "SMB signing is not enforced, enabling relay attacks.",
     "Enforce SMB signing via Group Policy.", False),
]

HEADERS_A = [
    "Finding", "Severity", "Target", "Object Type", "Domain",
    "Description", "Recommendation", "Exploitable",
]
HEADERS_B = [
    "Vulnerability", "Risk Severity", "Affected Asset", "Entity Type", "Environment",
    "Details", "Mitigation", "Confirmed",
]


def write_csv(path: Path, headers: list[str], rows: list[tuple], exploit_values: tuple[str, str]) -> None:
    true_val, false_val = exploit_values
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for title, severity, asset, asset_type, description, recommendation, exploitable in rows:
            writer.writerow([
                title, severity, asset, asset_type, DOMAIN,
                description, recommendation, true_val if exploitable else false_val,
            ])


def write_json(path: Path, assessment_name: str, rows: list[tuple]) -> None:
    """Genuinely JSON-shaped (nested `asset` object, not flattened columns)
    so this exercises the JSON parser's nested-asset-object handling for
    real, not just "a CSV row re-encoded as JSON"."""
    payload = {
        "scan_metadata": {"tool": "Pentera", "assessment_name": assessment_name},
        "findings": [
            {
                "finding": title,
                "severity": severity,
                "asset": {"name": asset, "type": asset_type, "domain": DOMAIN},
                "description": description,
                "recommendation": recommendation,
                "exploitable": exploitable,
            }
            for title, severity, asset, asset_type, description, recommendation, exploitable in rows
        ],
    }
    with path.open("w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)

    assessment_1_rows = FINDINGS
    resolved = RESOLVED_TITLES_ASSETS
    assessment_2_rows = [
        row for row in FINDINGS if (row[0], row[2]) not in resolved
    ] + NEW_IN_ASSESSMENT_2

    resolved_3 = RESOLVED_TITLES_ASSETS_3
    assessment_3_rows = [
        row for row in assessment_2_rows if (row[0], row[2]) not in resolved_3
    ] + NEW_IN_ASSESSMENT_3

    write_csv(OUT_DIR / "pentera_assessment_1_2026-05-15.csv", HEADERS_A, assessment_1_rows, ("true", "false"))
    write_csv(OUT_DIR / "pentera_assessment_2_2026-07-15.csv", HEADERS_B, assessment_2_rows, ("Yes", "No"))
    write_json(
        OUT_DIR / "pentera_assessment_3_2026-09-15.json",
        "Fabrikam AD Assessment - September 2026",
        assessment_3_rows,
    )

    print(f"Assessment 1 (CSV): {len(assessment_1_rows)} rows")
    print(f"Assessment 2 (CSV): {len(assessment_2_rows)} rows "
          f"({len(resolved)} resolved, {len(assessment_2_rows) - len(NEW_IN_ASSESSMENT_2)} recurring, "
          f"{len(NEW_IN_ASSESSMENT_2)} new)")
    print(f"Assessment 3 (JSON): {len(assessment_3_rows)} rows "
          f"({len(resolved_3)} resolved, {len(assessment_3_rows) - len(NEW_IN_ASSESSMENT_3)} recurring, "
          f"{len(NEW_IN_ASSESSMENT_3)} new)")


if __name__ == "__main__":
    main()
