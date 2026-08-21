"""Orchestrates a Pentera CSV or JSON import end-to-end.

Pentera CSV/JSON -> format-specific parser -> mapper -> (fingerprint,
Asset/Finding upsert, FindingInstance creation, risk scoring) -> Assessment
summary. Both formats share the exact same mapper and downstream logic
(_import_parsed_rows) — only the parsing step differs.

This is the only place in the application that imports from
`app.integrations.pentera` — everything downstream (routers, dashboard,
frontend) only ever sees the internal Finding/FindingInstance model.
"""
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.integrations.pentera import json_parser, mapper, parser
from app.integrations.pentera.parser import ParseError
from app.integrations.pentera.schemas import NormalizedFinding, RawPenteraRow
from app.models.asset import Asset
from app.models.assessment import Assessment
from app.models.finding import Finding
from app.models.finding_instance import FindingInstance
from app.services.fingerprint import compute_fingerprint
from app.services.risk_engine import compute_risk

TERMINAL_RESOLVED_STATUSES = {"VALIDATED", "CLOSED"}

log = get_logger("import")


@dataclass
class ImportSummary:
    assessment_id: int
    rows_processed: int = 0
    rows_imported: int = 0
    rows_skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    unknown_mappings: int = 0
    new_findings: int = 0
    recurring_findings: int = 0
    resolved_findings: int = 0
    # Source records within THIS SAME assessment that fingerprinted to a
    # logical Finding already observed earlier in this same import (exact
    # duplicates, or superficially-different records normalizing to the
    # same (type, domain, asset) triple). Coalesced into the one
    # FindingInstance the UNIQUE(finding_id, assessment_id) constraint
    # allows -- never counted as new/recurring, which describe
    # cross-assessment history, not repeats within one file.
    duplicate_observations_coalesced: int = 0
    # Pentera JSON-only: how many objects were found in the source file's
    # "achievements" / "vulnerabilities" collections, regardless of how
    # many of those became FindingInstances. 0 for a CSV import, or a JSON
    # import whose export didn't contain that collection at all. See
    # json_parser.py / docs/PENTERA_IMPORT.md "Architecture: achievements
    # vs. vulnerabilities".
    achievements_discovered: int = 0
    vulnerabilities_discovered: int = 0
    # Distinct logical Findings (new + recurring) this import actually
    # created or touched -- i.e. the number of real remediation items a
    # user will see for this assessment, after intra-assessment duplicate
    # coalescing. Distinguishes "how many Findings do I need to act on"
    # from rows_imported (raw source record count, e.g. 15,982 achievement
    # objects before coalescing).
    remediation_findings_created: int = 0


def _get_or_create_asset(db: Session, nf: NormalizedFinding) -> Asset:
    identifier = nf.asset_external_identifier.strip().lower()
    domain = nf.domain.strip().lower()

    asset = (
        db.query(Asset)
        .filter(
            Asset.external_identifier.ilike(identifier),
            Asset.domain.ilike(domain),
            Asset.asset_type == nf.asset_type,
        )
        .first()
    )
    if asset is None:
        asset = Asset(
            external_identifier=nf.asset_external_identifier,
            name=nf.asset_name,
            asset_type=nf.asset_type,
            domain=nf.domain,
            criticality="medium",
        )
        db.add(asset)
        db.flush()

    if nf.tier_zero and asset.criticality != "critical":
        asset.criticality = "critical"
        asset.tier = "0"

    return asset


def _get_or_create_finding(
    db: Session, fingerprint: str, nf: NormalizedFinding, asset: Asset, assessment_date: date
) -> tuple[Finding, bool]:
    """Returns (finding, is_new)."""
    finding = db.query(Finding).filter(Finding.fingerprint == fingerprint).first()
    is_new = finding is None

    if finding is None:
        finding = Finding(
            fingerprint=fingerprint,
            normalized_type=nf.normalized_type,
            title=nf.title,
            category=nf.category,
            asset_id=asset.id,
            severity=nf.severity,
            status="OPEN",
            first_seen=assessment_date,
            last_seen=assessment_date,
            currently_present=True,
            remediation_guidance=nf.remediation_guidance,
            description=nf.description,
            source_metadata=nf.source_metadata,
        )
        db.add(finding)
        db.flush()
    else:
        # Refresh display fields with the latest observation; keep workflow
        # state (status/owner) untouched — re-importing must never silently
        # discard remediation progress.
        finding.title = nf.title
        finding.category = nf.category
        finding.severity = nf.severity
        finding.remediation_guidance = finding.remediation_guidance or nf.remediation_guidance
        finding.description = finding.description or nf.description
        finding.source_metadata = nf.source_metadata
        finding.currently_present = True
        if assessment_date > finding.last_seen:
            finding.last_seen = assessment_date
        if assessment_date < finding.first_seen:
            finding.first_seen = assessment_date
        if finding.status in TERMINAL_RESOLVED_STATUSES:
            finding.status = "REOPENED"

    return finding, is_new


def import_pentera_csv(
    db: Session,
    content: bytes,
    *,
    name: str,
    assessment_date: date,
    environment: str | None,
    source_filename: str | None,
    notes: str | None,
) -> ImportSummary:
    log.info("Pentera CSV import started: file_size_bytes=%d", len(content))

    try:
        raw_rows, parse_warnings = parser.parse_csv(content)
    except ParseError as exc:
        log.warning("Pentera CSV import failed at parse stage: %s", type(exc).__name__)
        raise

    return _import_parsed_rows(
        db,
        raw_rows,
        parse_warnings,
        name=name,
        assessment_date=assessment_date,
        environment=environment,
        source_filename=source_filename,
        notes=notes,
    )


def import_pentera_json(
    db: Session,
    content: bytes,
    *,
    name: str,
    assessment_date: date,
    environment: str | None,
    source_filename: str | None,
    notes: str | None,
) -> ImportSummary:
    """Same contract as import_pentera_csv, for a Pentera JSON export.

    See json_parser.py's module docstring: structurally defensive, not yet
    validated against a real Pentera JSON export.
    """
    log.info("Pentera JSON import started: file_size_bytes=%d", len(content))

    try:
        raw_rows, parse_warnings, collection_counts = json_parser.parse_json(content)
    except ParseError as exc:
        log.warning("Pentera JSON import failed at parse stage: %s", type(exc).__name__)
        raise

    return _import_parsed_rows(
        db,
        raw_rows,
        parse_warnings,
        name=name,
        assessment_date=assessment_date,
        environment=environment,
        source_filename=source_filename,
        notes=notes,
        achievements_discovered=collection_counts.get("achievements_discovered", 0),
        vulnerabilities_discovered=collection_counts.get("vulnerabilities_discovered", 0),
    )


def _import_parsed_rows(
    db: Session,
    raw_rows: list[RawPenteraRow],
    parse_warnings: list[str],
    *,
    name: str,
    assessment_date: date,
    environment: str | None,
    source_filename: str | None,
    notes: str | None,
    achievements_discovered: int = 0,
    vulnerabilities_discovered: int = 0,
) -> ImportSummary:
    """Shared core for both CSV and JSON imports, starting from the same
    RawPenteraRow shape either parser produces: mapper -> fingerprint ->
    Asset/Finding upsert -> FindingInstance -> risk scoring -> Assessment
    summary. This is the ONLY place that logic lives — CSV and JSON never
    diverge past this point.
    """
    result = mapper.map_rows(raw_rows)
    warnings = parse_warnings + result.warnings
    unknown_count = sum(1 for nf in result.findings if nf.normalized_type == "UNKNOWN")

    # Everything from here through db.commit() is one atomic unit: any
    # exception rolls the whole attempt back explicitly (not relying on
    # get_db()'s close()-implies-rollback behavior, which is real but not
    # the place to document/guarantee this contract) so a failed import
    # never leaves a partial Assessment/Finding/FindingInstance/Asset
    # behind. See test_import_atomicity.py.
    try:
        assessment = Assessment(
            name=name,
            source="pentera",
            assessment_date=assessment_date,
            environment=environment,
            source_filename=source_filename,
            notes=notes,
            rows_processed=result.rows_processed,
            rows_imported=len(result.findings),
            rows_skipped=result.rows_skipped,
            import_warnings=warnings,
        )
        db.add(assessment)
        db.flush()

        new_count = 0
        recurring_count = 0
        duplicate_count = 0
        seen_fingerprints: set[str] = set()
        seen_finding_ids: set[int] = set()
        domains_in_batch: set[str] = set()
        # Track how many source records (including duplicates) coalesced
        # into each fingerprint's single FindingInstance, so the count is
        # visible on the instance itself rather than only in the aggregate
        # ImportSummary -- e.g. an achievement observed 40 times in one
        # Pentera export becomes one FindingInstance with occurrence_count
        # 40, not 40 rows or 1 row with the repetition silently lost.
        instance_by_fingerprint: dict[str, FindingInstance] = {}
        occurrence_count_by_fingerprint: dict[str, int] = {}

        for nf in result.findings:
            # canonical_title is part of identity, not just normalized_type
            # -- see services/fingerprint.py's module docstring and
            # docs/PENTERA_IMPORT.md "Achievement identity" for why: many
            # distinct Pentera Achievement names are either UNKNOWN or share
            # one normalized_type/category, and must not collapse into one
            # Finding just because normalized_type/domain/asset match.
            fingerprint = compute_fingerprint(
                nf.normalized_type, nf.domain, nf.asset_external_identifier, nf.canonical_title
            )

            if fingerprint in seen_fingerprints:
                occurrence_count_by_fingerprint[fingerprint] = occurrence_count_by_fingerprint.get(fingerprint, 1) + 1
                # Intra-assessment duplicate: another source record earlier
                # in THIS SAME import already resolved to this exact
                # logical finding (identical records, or superficially
                # different ones that normalize to the same
                # (type, domain, asset) triple — e.g. multiple
                # evidence/attack-path records for one issue, or the same
                # affected object reported under more than one module).
                # Real Pentera exports can legitimately do this. Collapse
                # into the single FindingInstance the
                # UNIQUE(finding_id, assessment_id) constraint requires —
                # never attempt a second one — and don't touch the Finding
                # again (it was already fully populated by the first
                # occurrence; re-applying a duplicate's fields here could
                # desync finding.severity from finding.risk_score, which is
                # only recomputed below for the first occurrence). Not
                # counted as new or recurring: those describe
                # cross-assessment history, not repeats within one file.
                duplicate_count += 1
                continue
            seen_fingerprints.add(fingerprint)

            asset = _get_or_create_asset(db, nf)
            finding, is_new = _get_or_create_finding(db, fingerprint, nf, asset, assessment_date)

            instance = FindingInstance(
                finding_id=finding.id,
                assessment_id=assessment.id,
                source_severity=nf.severity,
                source_title=nf.source_title,
                raw_row=nf.raw_row,
                observed_at=assessment_date,
            )
            db.add(instance)
            instance_by_fingerprint[fingerprint] = instance
            occurrence_count_by_fingerprint[fingerprint] = 1

            risk = compute_risk(
                severity=finding.severity,
                tier_zero=nf.tier_zero,
                privileged=nf.privileged,
                credential_exposure=nf.credential_exposure,
                exploitable=nf.exploitable,
                asset_criticality=asset.criticality,
            )
            finding.risk_score = risk.score
            finding.priority = risk.priority
            finding.risk_reasons = risk.reasons

            if is_new:
                new_count += 1
            else:
                recurring_count += 1
            seen_finding_ids.add(finding.id)
            domains_in_batch.add(nf.domain.strip().lower())

        for fingerprint, instance in instance_by_fingerprint.items():
            instance.occurrence_count = occurrence_count_by_fingerprint.get(fingerprint, 1)

        if duplicate_count:
            warnings.append(
                f"{duplicate_count} source record(s) were duplicate observations of an "
                "already-imported finding within this same assessment and were coalesced "
                "into a single record (not counted as new or recurring)."
            )
            # Reassign (not mutate in place) so SQLAlchemy's change-tracking
            # picks it up for the JSON column -- appending to the list
            # object after it was already assigned to import_warnings would
            # not reliably be detected as a change to flush/persist.
            assessment.import_warnings = warnings

        db.flush()

        # Anything previously "present" in one of the domains covered by this
        # assessment, but not observed this time, is now considered resolved /
        # no longer observed.
        resolved_count = 0
        if domains_in_batch:
            candidates = (
                db.query(Finding)
                .join(Asset, Finding.asset_id == Asset.id)
                .filter(Finding.currently_present.is_(True))
                .filter(Asset.domain.in_(domains_in_batch))
                .all()
            )
            for f in candidates:
                if f.id not in seen_finding_ids:
                    f.currently_present = False
                    resolved_count += 1

        # Assessment-level aggregate risk score: mean risk score of findings that
        # were present in this specific assessment (simple, explainable).
        if seen_finding_ids:
            findings_in_assessment = db.query(Finding).filter(Finding.id.in_(seen_finding_ids)).all()
            assessment.risk_score = round(
                sum(f.risk_score for f in findings_in_assessment) / len(findings_in_assessment), 1
            )
        else:
            assessment.risk_score = 0

        db.commit()
    except Exception:
        db.rollback()
        raise

    log.info(
        "Pentera import completed: assessment_id=%d rows_processed=%d rows_imported=%d "
        "rows_skipped=%d warnings=%d unknown=%d new=%d recurring=%d resolved=%d duplicates=%d "
        "achievements_discovered=%d vulnerabilities_discovered=%d",
        assessment.id,
        result.rows_processed,
        len(result.findings),
        result.rows_skipped,
        len(warnings),
        unknown_count,
        new_count,
        recurring_count,
        resolved_count,
        duplicate_count,
        achievements_discovered,
        vulnerabilities_discovered,
    )

    return ImportSummary(
        assessment_id=assessment.id,
        rows_processed=result.rows_processed,
        rows_imported=len(result.findings),
        rows_skipped=result.rows_skipped,
        warnings=warnings,
        unknown_mappings=unknown_count,
        new_findings=new_count,
        recurring_findings=recurring_count,
        resolved_findings=resolved_count,
        duplicate_observations_coalesced=duplicate_count,
        achievements_discovered=achievements_discovered,
        vulnerabilities_discovered=vulnerabilities_discovered,
        remediation_findings_created=len(seen_finding_ids),
    )
