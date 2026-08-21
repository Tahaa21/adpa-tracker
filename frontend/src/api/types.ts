// Mirrors backend/app/schemas/*.py — keep in sync manually (small MVP, no
// codegen needed yet).

export type Priority = 'P1' | 'P2' | 'P3' | 'P4'

export type FindingStatus =
  | 'OPEN'
  | 'TRIAGED'
  | 'ASSIGNED'
  | 'IN_REMEDIATION'
  | 'READY_FOR_VALIDATION'
  | 'VALIDATED'
  | 'CLOSED'
  | 'RISK_ACCEPTED'
  | 'FALSE_POSITIVE'
  | 'DEFERRED'
  | 'REOPENED'

export const ALL_STATUSES: FindingStatus[] = [
  'OPEN',
  'TRIAGED',
  'ASSIGNED',
  'IN_REMEDIATION',
  'READY_FOR_VALIDATION',
  'VALIDATED',
  'CLOSED',
  'RISK_ACCEPTED',
  'FALSE_POSITIVE',
  'DEFERRED',
  'REOPENED',
]

export interface Owner {
  id: number
  name: string
  team?: string | null
  email?: string | null
}

export interface Asset {
  id: number
  external_identifier: string
  name: string
  asset_type: string
  domain: string
  criticality: string
  tier?: string | null
}

export interface FindingInstance {
  id: number
  assessment_id: number
  source_severity?: string | null
  source_title?: string | null
  observed_at: string
  occurrence_count: number
}

export interface Remediation {
  id: number
  finding_id: number
  owner_id?: number | null
  status: string
  recommended_action?: string | null
  remediation_notes?: string | null
  due_date?: string | null
  created_at: string
  updated_at: string
}

export interface ValidationRecord {
  id: number
  finding_id: number
  validation_method?: string | null
  evidence?: string | null
  validation_date: string
  result: 'PASS' | 'FAIL' | 'INCONCLUSIVE'
  validated_by?: string | null
  notes?: string | null
}

export interface FindingListItem {
  id: number
  normalized_type: string
  title: string
  category: string
  severity: string
  risk_score: number
  priority: Priority
  status: FindingStatus
  first_seen: string
  last_seen: string
  currently_present: boolean
  asset: Asset
  owner?: Owner | null
  // Raw Pentera numeric severity (e.g. 8.3), shown alongside risk_score --
  // null for CSV imports / findings without a numeric source severity.
  pentera_numeric_severity?: number | null
  // How many source records coalesced into the most recent
  // FindingInstance (e.g. Pentera's own "239 occurrences" count for an
  // Achievement type). 1 for a normal, non-duplicated finding.
  occurrence_count: number
}

export interface FindingDetail extends FindingListItem {
  risk_reasons: string[]
  remediation_guidance?: string | null
  description?: string | null
  source_metadata: Record<string, unknown>
  fingerprint: string
  instances: FindingInstance[]
  remediations: Remediation[]
  validations: ValidationRecord[]
}

export interface Assessment {
  id: number
  name: string
  source: string
  assessment_date: string
  imported_at: string
  environment?: string | null
  source_filename?: string | null
  notes?: string | null
  risk_score?: number | null
  rows_processed: number
  rows_imported: number
  rows_skipped: number
  import_warnings: string[]
}

export interface ImportSummary {
  assessment_id: number
  rows_processed: number
  rows_imported: number
  rows_skipped: number
  warnings: string[]
  unknown_mappings: number
  new_findings: number
  recurring_findings: number
  resolved_findings: number
  duplicate_observations_coalesced: number
  achievements_discovered: number
  vulnerabilities_discovered: number
  remediation_findings_created: number
}

export interface PriorityDistribution {
  P1: number
  P2: number
  P3: number
  P4: number
}

export interface SeverityDistribution {
  critical: number
  high: number
  medium: number
  low: number
}

export interface AssessmentDetail {
  assessment: Assessment
  priority_distribution: PriorityDistribution
  findings_observed: number
  previous_assessment_id?: number | null
  previous_risk_score?: number | null
  risk_reduction_pct?: number | null
  new_findings: number
  recurring_findings: number
  resolved_findings: number
}

export interface TopMetrics {
  total_findings: number
  open_findings: number
  p1_findings: number
  validated_findings: number
  overall_risk_score: number
}

export interface RemediationMetrics {
  assigned: number
  in_remediation: number
  ready_for_validation: number
  validated: number
}

export interface AssessmentComparison {
  previous_assessment_id?: number | null
  previous_assessment_name?: string | null
  previous_risk_score?: number | null
  current_assessment_id?: number | null
  current_assessment_name?: string | null
  current_risk_score?: number | null
  risk_reduction_pct?: number | null
  new_findings: number
  recurring_findings: number
  resolved_findings: number
}

export interface Dashboard {
  top_metrics: TopMetrics
  remediation_metrics: RemediationMetrics
  priority_distribution: PriorityDistribution
  severity_distribution: SeverityDistribution
  category_distribution: Record<string, number>
  comparison?: AssessmentComparison | null
  assessment_count: number
}
