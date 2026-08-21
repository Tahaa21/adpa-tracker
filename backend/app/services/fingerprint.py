"""Deterministic fingerprinting for finding deduplication across assessments.

See docs/PENTERA_IMPORT.md ("Fingerprinting / deduplication" and
"Achievement identity") for the full rationale.

One logical Finding per (normalized_type, discriminator, domain, asset)
tuple. `discriminator` is expected to be a *canonicalized source title* in
practice — see `mapper.py`'s `NormalizedFinding.canonical_title` and
`import_service.py`'s call site — NOT just left to default to
`normalized_type` as it used to be. That default is kept here only for
direct unit tests of this function in isolation; every real caller passes
an explicit discriminator.

Why the title matters: `normalized_type` alone is too coarse once a real
Pentera export is involved. Many distinct Pentera Achievement conditions
either don't match any TYPE_RULES keyword pattern (normalized_type =
UNKNOWN for all of them) or deliberately share one normalized_type/category
(e.g. "Password can be cracked using low GPU effort" and "...using high GPU
effort" are both WEAK_PASSWORD) while still being different, separately
actionable remediation items. Without the title in the fingerprint, EVERY
achievement sharing (normalized_type, domain, asset) — which includes every
domain-level UNKNOWN achievement with no specific affected object, since
those all fall back to the same (domain, domain) pair — collapses into one
Finding. That was the real-world bug: 16k achievement objects across many
distinct Pentera Achievement types collapsed to 7 logical findings. See
docs/PENTERA_IMPORT.md "Achievement identity" for the full incident and the
known tradeoff this introduces (a renamed Achievement string between
assessment runs is treated as a new logical Finding, not a recurrence).
"""
import hashlib


def compute_fingerprint(
    normalized_type: str,
    domain: str,
    asset_external_identifier: str,
    discriminator: str | None = None,
) -> str:
    discriminator = discriminator or normalized_type
    key = "|".join(
        [
            normalized_type.strip().upper(),
            (domain or "").strip().lower(),
            (asset_external_identifier or "").strip().lower(),
            discriminator.strip().upper(),
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
