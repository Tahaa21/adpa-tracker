import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { AssessmentDetail as AssessmentDetailType } from '../api/types'
import { Card, ErrorState, LoadingState, PageHeader, StatCard } from '../components/Card'
import { formatDate, formatDateTime } from '../utils/format'

export default function AssessmentDetail() {
  const { id } = useParams()
  const [detail, setDetail] = useState<AssessmentDetailType | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    api
      .getAssessment(Number(id))
      .then(setDetail)
      .catch((e) => setError(e.message))
  }, [id])

  if (error) return <ErrorState message={error} />
  if (!detail) return <LoadingState />

  const { assessment, priority_distribution, findings_observed, previous_risk_score, risk_reduction_pct, new_findings, recurring_findings, resolved_findings } = detail

  return (
    <div>
      <PageHeader
        title={assessment.name}
        subtitle={`${assessment.source.toUpperCase()} · Assessed ${formatDate(assessment.assessment_date)} · Imported ${formatDateTime(assessment.imported_at)}`}
        actions={
          <Link to="/findings" className="text-sm text-sky-400 hover:underline">
            View all findings →
          </Link>
        }
      />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Findings Observed" value={findings_observed} />
        <StatCard label="P1" value={priority_distribution.P1} accent="red" />
        <StatCard label="P2" value={priority_distribution.P2} accent="amber" />
        <StatCard label="P3" value={priority_distribution.P3} accent="sky" />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-slate-200">Assessment Info</h2>
          <dl className="space-y-2 text-sm">
            <Row label="Source File" value={assessment.source_filename ?? '—'} />
            <Row label="Environment" value={assessment.environment ?? '—'} />
            <Row label="Risk Score" value={String(assessment.risk_score ?? '—')} />
            <Row label="Rows Processed" value={String(assessment.rows_processed)} />
            <Row label="Rows Imported" value={String(assessment.rows_imported)} />
            <Row label="Rows Skipped" value={String(assessment.rows_skipped)} />
            <Row label="Notes" value={assessment.notes ?? '—'} />
          </dl>
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-semibold text-slate-200">Comparison vs. Previous Assessment</h2>
          {previous_risk_score == null ? (
            <p className="text-sm text-slate-500">No previous assessment to compare against.</p>
          ) : (
            <div className="grid grid-cols-2 gap-4 text-sm">
              <Row label="Previous Risk Score" value={String(previous_risk_score)} />
              <Row
                label="Risk Reduction"
                value={risk_reduction_pct != null ? `${risk_reduction_pct}%` : '—'}
                accent={risk_reduction_pct != null && risk_reduction_pct >= 0 ? 'emerald' : 'red'}
              />
              <Row label="New Findings" value={String(new_findings)} accent="amber" />
              <Row label="Recurring Findings" value={String(recurring_findings)} />
              <Row label="Resolved / No Longer Observed" value={String(resolved_findings)} accent="emerald" />
            </div>
          )}
        </Card>
      </div>

      {assessment.import_warnings.length > 0 && (
        <Card className="mt-6">
          <h2 className="mb-3 text-sm font-semibold text-amber-400">
            Import Warnings ({assessment.import_warnings.length})
          </h2>
          <ul className="max-h-64 overflow-y-auto text-xs text-slate-400">
            {assessment.import_warnings.map((w, i) => (
              <li key={i} className="border-t border-slate-800/60 py-1.5 first:border-0">
                {w}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}

function Row({ label, value, accent }: { label: string; value: string; accent?: 'emerald' | 'red' | 'amber' }) {
  const color = accent === 'emerald' ? 'text-emerald-400' : accent === 'red' ? 'text-red-400' : accent === 'amber' ? 'text-amber-400' : 'text-slate-100'
  return (
    <div className="flex items-center justify-between border-b border-slate-800/50 py-1.5 last:border-0">
      <dt className="text-slate-500">{label}</dt>
      <dd className={`font-medium ${color}`}>{value}</dd>
    </div>
  )
}
