import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api/client'
import type { Dashboard } from '../api/types'
import { Card, EmptyState, ErrorState, LoadingState, PageHeader, StatCard } from '../components/Card'
import { titleCase } from '../utils/format'

const PRIORITY_COLORS: Record<string, string> = { P1: '#f87171', P2: '#fbbf24', P3: '#38bdf8', P4: '#64748b' }
const SEVERITY_COLORS: Record<string, string> = { critical: '#f87171', high: '#fb923c', medium: '#fbbf24', low: '#64748b' }
const CATEGORY_COLOR = '#38bdf8'

export default function Overview() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .getDashboard()
      .then(setDashboard)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingState label="Loading dashboard…" />
  if (error) return <ErrorState message={error} />
  if (!dashboard) return null

  const {
    top_metrics,
    remediation_metrics,
    priority_distribution,
    severity_distribution,
    category_distribution,
    comparison,
    assessment_count,
  } = dashboard

  const priorityData = (['P1', 'P2', 'P3', 'P4'] as const).map((p) => ({
    name: p,
    value: priority_distribution[p],
  }))

  const severityData = (['critical', 'high', 'medium', 'low'] as const).map((s) => ({
    name: titleCase(s),
    key: s,
    value: severity_distribution[s],
  }))

  const categoryData = Object.entries(category_distribution)
    .map(([name, value]) => ({ name: titleCase(name), value }))
    .sort((a, b) => b.value - a.value)

  const funnelSteps = [
    { label: 'Assigned', value: remediation_metrics.assigned },
    { label: 'In Remediation', value: remediation_metrics.in_remediation },
    { label: 'Ready for Validation', value: remediation_metrics.ready_for_validation },
    { label: 'Validated', value: remediation_metrics.validated },
  ]

  return (
    <div>
      <PageHeader
        title="Overview"
        subtitle="What to fix first, who owns it, and whether risk is actually going down."
        actions={
          <Link
            to="/assessments"
            className="rounded-md bg-sky-500 px-4 py-2 text-sm font-medium text-white hover:bg-sky-400"
          >
            + New Assessment
          </Link>
        }
      />

      {assessment_count === 0 ? (
        <EmptyState message="No assessments imported yet. Go to Assessments → New Assessment to upload a Pentera JSON or CSV export." />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
            <StatCard label="Total Findings" value={top_metrics.total_findings} />
            <StatCard label="Open Findings" value={top_metrics.open_findings} accent="amber" />
            <StatCard label="P1 Findings" value={top_metrics.p1_findings} accent="red" />
            <StatCard label="Validated" value={top_metrics.validated_findings} accent="emerald" />
            <StatCard label="Overall Risk Score" value={top_metrics.overall_risk_score} accent="sky" />
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-4">
            {funnelSteps.map((s) => (
              <Card key={s.label}>
                <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">{s.label}</div>
                <div className="mt-2 text-2xl font-semibold text-slate-100">{s.value}</div>
              </Card>
            ))}
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <h2 className="mb-1 text-sm font-semibold text-slate-200">Tracker Priority Distribution</h2>
              <p className="mb-3 text-xs text-slate-500">
                Our remediation prioritization (Pentera severity + context — Tier 0, privileged access, credential
                exposure, exploitability, asset criticality).
              </p>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={priorityData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={3}>
                    {priorityData.map((entry) => (
                      <Cell key={entry.name} fill={PRIORITY_COLORS[entry.name]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: '#101a2e', border: '1px solid #1e293b', borderRadius: 8 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="mt-2 flex justify-center gap-4 text-xs">
                {priorityData.map((entry) => (
                  <div key={entry.name} className="flex items-center gap-1.5">
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: PRIORITY_COLORS[entry.name] }}
                    />
                    <span className="text-slate-400">
                      {entry.name}: {entry.value}
                    </span>
                  </div>
                ))}
              </div>
            </Card>

            <Card>
              <h2 className="mb-1 text-sm font-semibold text-slate-200">Pentera Severity Distribution</h2>
              <p className="mb-3 text-xs text-slate-500">
                Raw source severity rating, before any Tracker context is applied.
              </p>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={severityData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={3}>
                    {severityData.map((entry) => (
                      <Cell key={entry.key} fill={SEVERITY_COLORS[entry.key]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: '#101a2e', border: '1px solid #1e293b', borderRadius: 8 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="mt-2 flex justify-center gap-4 text-xs">
                {severityData.map((entry) => (
                  <div key={entry.key} className="flex items-center gap-1.5">
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: SEVERITY_COLORS[entry.key] }}
                    />
                    <span className="text-slate-400">
                      {entry.name}: {entry.value}
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4">
            <Card>
              <h2 className="mb-4 text-sm font-semibold text-slate-200">Category Distribution</h2>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={categoryData} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                  <XAxis type="number" stroke="#64748b" fontSize={12} allowDecimals={false} />
                  <YAxis type="category" dataKey="name" stroke="#64748b" fontSize={12} width={140} />
                  <Tooltip
                    contentStyle={{ background: '#101a2e', border: '1px solid #1e293b', borderRadius: 8 }}
                    cursor={{ fill: 'rgba(148,163,184,0.08)' }}
                  />
                  <Bar dataKey="value" fill={CATEGORY_COLOR} radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>

          <div className="mt-6">
            <Card>
              <h2 className="mb-4 text-sm font-semibold text-slate-200">Assessment-over-Assessment Comparison</h2>
              {!comparison ? (
                <EmptyState message="Import a second assessment to see risk-reduction trends." />
              ) : (
                <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
                  <div>
                    <div className="text-xs text-slate-500">Previous Risk Score</div>
                    <div className="mt-1 text-xl font-semibold text-slate-300">
                      {comparison.previous_risk_score ?? '—'}
                    </div>
                    <div className="text-[11px] text-slate-500">{comparison.previous_assessment_name}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Current Risk Score</div>
                    <div className="mt-1 text-xl font-semibold text-slate-100">
                      {comparison.current_risk_score ?? '—'}
                    </div>
                    <div className="text-[11px] text-slate-500">{comparison.current_assessment_name}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Risk Reduction</div>
                    <div
                      className={`mt-1 text-xl font-semibold ${
                        (comparison.risk_reduction_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'
                      }`}
                    >
                      {comparison.risk_reduction_pct != null ? `${comparison.risk_reduction_pct}%` : '—'}
                    </div>
                  </div>
                  <div className="flex gap-4">
                    <div>
                      <div className="text-xs text-slate-500">New</div>
                      <div className="mt-1 text-xl font-semibold text-amber-400">{comparison.new_findings}</div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">Recurring</div>
                      <div className="mt-1 text-xl font-semibold text-slate-300">
                        {comparison.recurring_findings}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">Resolved</div>
                      <div className="mt-1 text-xl font-semibold text-emerald-400">
                        {comparison.resolved_findings}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
