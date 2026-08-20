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
    "credential",  # also matches "credentials" (substring, post-normalize)
    "secret",
    "hash",  # also matches "nt hash", "lm hash", "ntlm hash", "password hash"
    "ntlm",
    "cracked",  # e.g. a bare "Cracked" or "Cracked Value" column
    "cleartext",
    "plaintext",
    "privatekey",
    "apikey",
    "token",
    "evidence",  # Pentera credential findings often put the leaked/cracked
    # value itself in an "Evidence" column.
]

REDACTED_MARKER = "[REDACTED - sensitive field, value not stored]"

# Defense-in-depth for free-text fields (description/recommendation) that
# aren't their own dedicated column: catches the common "key: value" /
# "key=value" shape, e.g. "Account svc_backup password = Summer2024!" ->
# "Account svc_backup password: [REDACTED]". This is intentionally narrow —
# it matches an explicit key/value pairing, not arbitrary prose, because a
# broader pattern would false-positive heavily on legitimate remediation
# guidance that discusses passwords without stating one (e.g. "reset the
# password"). Known limitation: prose that states a secret without a
# key/value delimiter (e.g. "the password is Summer2024!") is NOT caught by
# this — see docs/LOCAL_DATA_SECURITY.md.
_INLINE_CREDENTIAL_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|credential(?:s)?|secret|token|api[_ ]?key|"
    r"cleartext|plaintext|nt\s*hash|lm\s*hash|ntlm(?:\s*hash)?|hash)\b"
    r"(\s*[:=]\s*)(\S+)"
)


def _normalize_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", header.lower().strip())


def is_sensitive_header(header: str) -> bool:
    normalized = _normalize_header(header)
    return any(pattern in normalized for pattern in SENSITIVE_HEADER_PATTERNS)


def redact_row(raw: dict[str, str]) -> dict[str, str]:
    """Return a copy of a raw CSV row dict with sensitive-looking values
    redacted, in two passes:

    1. Any column whose HEADER matches a sensitive pattern has its entire
       value replaced with the fixed marker (handles a dedicated
       "Password"/"Evidence"/etc. column).
    2. Any surviving value (from a column whose header did NOT match) is
       still scanned for an inline "key: value" credential pattern (handles
       e.g. a generic "Notes" column that happens to contain
       "password: X123"). This matters because unmapped columns are
       returned to the API via Finding.source_metadata.unmapped_fields, so
       both passes run before anything is persisted, not just the first.
    """
    redacted: dict[str, str] = {}
    for key, value in raw.items():
        if key is not None and is_sensitive_header(key) and value not in (None, ""):
            redacted[key] = REDACTED_MARKER
        elif isinstance(value, str):
            redacted[key] = redact_inline_credentials(value)
        else:
            redacted[key] = value
    return redacted


def redact_json(value: object) -> object:
    """Recursively redact a parsed-JSON value (dict/list/scalar) before it is
    ever persisted (Pentera JSON's raw finding objects and any nested
    "unmapped" sub-structures). Two passes, applied at every nesting depth:

    1. For a dict, any KEY matching a sensitive pattern (password, secret,
       credential, hash, ntlm, nt_hash, lm_hash, cracked_password,
       cleartext, plaintext, token, etc. — see SENSITIVE_HEADER_PATTERNS,
       matched via the same normalized-key comparison used for CSV headers)
       has its entire value replaced with the fixed marker, regardless of
       whether that value is a scalar, a nested object, or an array —
       a nested `{"credentials": {"username": "x", "password": "y"}}` is
       fully redacted at the `credentials` key, not just the `password`
       leaf, since the whole sub-tree is presumed sensitive once the key
       itself says so.
    2. Any surviving string value (leaf or otherwise) is scanned for an
       inline "key: value" / "key=value" credential pattern, same as the
       CSV path's free-text handling.

    Recurses through dicts and lists to arbitrary depth. Non-dict/list/str
    values (int, float, bool, None) pass through unchanged.
    """
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for key, sub_value in value.items():
            key_str = key if isinstance(key, str) else str(key)
            if is_sensitive_header(key_str) and sub_value not in (None, "", {}, []):
                redacted[key] = REDACTED_MARKER
            else:
                redacted[key] = redact_json(sub_value)
        return redacted
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    if isinstance(value, str):
        return redact_inline_credentials(value)
    return value


def redact_inline_credentials(text: str | None) -> str | None:
    """Redact "key: value" / "key=value" credential patterns embedded in
    free text (e.g. a Description or Recommendation column). Only the value
    half is replaced; the surrounding sentence and the key label stay
    readable so the finding itself ("credential exposure detected") is
    still useful. See module-level comment on _INLINE_CREDENTIAL_RE for
    scope/limits.
    """
    if not text:
        return text
    return _INLINE_CREDENTIAL_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
