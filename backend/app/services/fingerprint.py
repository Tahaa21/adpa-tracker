"""Deterministic fingerprinting for finding deduplication across assessments.

See docs/PENTERA_IMPORT.md for the full rationale. Kept intentionally simple
for the MVP: one logical Finding per (normalized_type, domain, asset) triple.
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
