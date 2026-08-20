"""Orchestrates a Pentera CSV import end-to-end.

Pentera CSV -> parser -> mapper -> (fingerprint, Asset/Finding upsert,
FindingInstance creation, risk scoring) -> Assessment summary.

This is the only place in the application that imports from
`app.integrations.pentera` — everything downstream (routers, dashboard,
frontend) only ever sees the internal Finding/FindingInstance model.
"""
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.integrations.pentera import mapper, parser
from app.integrations.pentera.parser import ParseError
from app.integrations.pentera.schemas import NormalizedFinding
from app.models.asset import Asset
from app.models.assessment import Assessment
from app.models.finding import Finding
from app.models.finding_instance import FindingInstance
from app.services.fingerprint import compute_fingerprint
from app.services.risk_engine import compute_risk

TERMINAL_RESOLVED_STATUSES = {"VALIDATED", "CLOSED"}


@dataclass
class ImportSummary:
    assessment_id: int
    rows_processed: int = 0
    rows_imported: int = 0
    rows_skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    new_findings: int = 0
    recurring_findings: int = 0
    resolved_findings: int = 0


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
    try:
        raw_rows, parse_warnings = parser.parse_csv(content)
    except ParseError:
        raise

    result = mapper.map_rows(raw_rows)
    warnings = parse_warnings + result.warnings

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
    seen_finding_ids: set[int] = set()
    domains_in_batch: set[str] = set()

    for nf in result.findings:
        asset = _get_or_create_asset(db, nf)
        fingerprint = compute_fingerprint(nf.normalized_type, nf.domain, nf.asset_external_identifier)
        finding, is_new = _get_or_create_finding(db, fingerprint, nf, asset, assessment_date)

        existing_instance = (
            db.query(FindingInstance)
            .filter(
                FindingInstance.finding_id == finding.id,
                FindingInstance.assessment_id == assessment.id,
            )
            .first()
        )
        if existing_instance is None:
            db.add(
                FindingInstance(
                    finding_id=finding.id,
                    assessment_id=assessment.id,
                    source_severity=nf.severity,
                    source_title=nf.source_title,
                    raw_row=nf.raw_row,
                    observed_at=assessment_date,
                )
            )

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

    return ImportSummary(
        assessment_id=assessment.id,
        rows_processed=result.rows_processed,
        rows_imported=len(result.findings),
        rows_skipped=result.rows_skipped,
        warnings=warnings,
        new_findings=new_count,
        recurring_findings=recurring_count,
        resolved_findings=resolved_count,
    )
