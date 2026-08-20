"""Redacts likely-sensitive raw values before they are persisted.

The Pentera adapter preserves raw CSV rows verbatim (in FindingInstance.raw_row
and Finding.source_metadata.unmapped_fields) for audit/traceability. That is
useful for legitimate columns, but a real Pentera export for a
LEAKED_CREDENTIAL / WEAK_PASSWORD / REVERSIBLE_ENCRYPTION finding may include
an actual cracked/leaked password or hash in some column (commonly named
things like "Evidence", "Cracked Password", "Password Hash", etc.).

This module redacts the VALUE of any column whose HEADER matches a known
sensitive-field pattern, applied uniformly to every row regardless of
normalized_type (a credential-shaped column could appear on any row, not
just ones the keyword classifier recognizes as credential-related). The
column name and the fact that a value was present are preserved; the value
itself is replaced with a fixed marker.
"""
import re

# Header patterns (matched against the same normalized-header form the
# parser uses: lowercased, non-alphanumeric characters stripped) that
# indicate the column value may itself be a secret rather than metadata
# about a secret.
SENSITIVE_HEADER_PATTERNS = [
    "password",
    "passwd",
    "pwd",
    "credential",
    "secret",
    "hash",
    "ntlm",
    "cleartext",
    "plaintext",
    "privatekey",
    "apikey",
    "token",
    "evidence",  # Pentera credential findings often put the leaked/cracked
    # value itself in an "Evidence" column.
]

REDACTED_MARKER = "[REDACTED - sensitive field, value not stored]"


def _normalize_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", header.lower().strip())


def is_sensitive_header(header: str) -> bool:
    normalized = _normalize_header(header)
    return any(pattern in normalized for pattern in SENSITIVE_HEADER_PATTERNS)


def redact_row(raw: dict[str, str]) -> dict[str, str]:
    """Return a copy of a raw CSV row dict with sensitive-looking values
    replaced by a fixed marker. Non-matching columns pass through unchanged.
    """
    redacted: dict[str, str] = {}
    for key, value in raw.items():
        if key is not None and is_sensitive_header(key) and value not in (None, ""):
            redacted[key] = REDACTED_MARKER
        else:
            redacted[key] = value
    return redacted
