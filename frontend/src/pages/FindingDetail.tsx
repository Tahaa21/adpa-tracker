import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { FindingDetail as FindingDetailType, FindingStatus, Owner } from '../api/types'
import { ALL_STATUSES } from '../api/types'
import { CategoryBadge, PriorityBadge, SeverityBadge, StatusBadge } from '../components/Badges'
import { Card, ErrorState, LoadingState, PageHeader } from '../components/Card'
import { formatDate, titleCase } from '../utils/format'

export default function FindingDetail() {
  const { id } = useParams()
  const [finding, setFinding] = useState<FindingDetailType | null>(null)
  const [owners, setOwners] = useState<Owner[]>([])
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  function load() {
    if (!id) return
    api.getFinding(Number(id)).then(setFinding).catch((e) => setError(e.message))
  }

  function loadOwners() {
    api.listOwners().then(setOwners).catch(() => {})
  }

  useEffect(load, [id])
  useEffect(loadOwners, [])

  if (error) return <ErrorState message={error} />
  if (!finding) return <LoadingState />

  async function handleOwnerChange(ownerId: string) {
    if (!finding) return
    setActionError(null)
    try {
      await api.updateFinding(finding.id, { owner_id: ownerId ? Number(ownerId) : null })
      load()
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Failed to update owner.')
    }
  }

  async function handleStatusChange(status: string) {
    if (!finding || !status) return
    setActionError(null)
    try {
      await api.updateFinding(finding.id, { status: status as FindingStatus })
      load()
    } catch (e) {
      setActionError(
        e instanceof ApiError
          ? e.message
          : 'Failed to update status.'
      )
    }
  }

  return (
    <div>
      <Link to="/findings" className="mb-4 inline-block text-sm text-sky-400 hover:underline">
        ← Back to Findings
      </Link>

      <PageHeader
        title={finding.title}
        subtitle={`${finding.normalized_type} · Asset: ${finding.asset.name} (${finding.asset.domain})`}
        actions={
          <div className="flex items-center gap-2">
            <PriorityBadge priority={finding.priority} />
            <StatusBadge status={finding.status} />
          </div>
        }
      />

      {actionError && (
        <div className="mb-4">
          <ErrorState message={actionError} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <h2 className="mb-3 text-sm font-semibold text-slate-200">Risk Explanation</h2>
            <div className="mb-3 flex items-center gap-3">
              <span className="text-3xl font-bold text-slate-100">{finding.risk_score}</span>
              <span className="text-sm text-slate-500">/ 100</span>
              <PriorityBadge priority={finding.priority} />
            </div>
            <ul className="space-y-1 text-sm">
              {finding.risk_reasons.map((r, i) => (
                <li key={i} className="flex items-start gap-2 text-slate-300">
                  <span className="mt-0.5 text-emerald-400">＋</span>
                  {r}
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <h2 className="mb-3 text-sm font-semibold text-slate-200">Details</h2>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <Info label="Category"><CategoryBadge category={finding.category} /></Info>
              <Info label="Severity"><SeverityBadge severity={finding.severity} /></Info>
              {finding.pentera_numeric_severity != null && (
                <Info label="Pentera Severity (source)" value={String(finding.pentera_numeric_severity)} mono />
              )}
              <Info label="Tracker Risk Score" value={`${finding.risk_score} / 100`} mono />
              {finding.occurrence_count > 1 && (
                <Info
                  label="Occurrence Count"
                  value={`${finding.occurrence_count.toLocaleString()} (latest assessment)`}
                />
              )}
              <Info label="Original Source Title" value={(finding.source_metadata?.source_title as string) ?? finding.title} />
              <Info label="Fingerprint" value={finding.fingerprint.slice(0, 16) + '…'} mono />
              <Info label="First Seen" value={formatDate(finding.first_seen)} />
              <Info label="Last Seen" value={formatDate(finding.last_seen)} />
              <Info label="Currently Present" value={finding.currently_present ? 'Yes' : 'No — resolved / no longer observed'} />
              <Info label="Asset Type" value={titleCase(finding.asset.asset_type)} />
              <Info label="Asset Criticality" value={titleCase(finding.asset.criticality)} />
              <Info label="Asset Identifier" value={finding.asset.external_identifier} mono />
            </dl>
            {finding.description && (
              <p className="mt-3 border-t border-slate-800 pt-3 text-sm text-slate-400">{finding.description}</p>
            )}
            {finding.remediation_guidance && (
              <div className="mt-3 border-t border-slate-800 pt-3">
                <div className="mb-1 text-xs font-medium text-slate-500 uppercase">Remediation Guidance</div>
                <p className="text-sm text-slate-300">{finding.remediation_guidance}</p>
              </div>
            )}
          </Card>

          <Card>
            <h2 className="mb-3 text-sm font-semibold text-slate-200">Assessment History</h2>
            {finding.instances.length === 0 ? (
              <p className="text-sm text-slate-500">No assessment instances recorded.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {finding.instances.map((inst) => (
                  <li key={inst.id} className="flex items-center justify-between border-b border-slate-800/50 py-1.5 last:border-0">
                    <Link to={`/assessments/${inst.assessment_id}`} className="text-sky-400 hover:underline">
                      Assessment #{inst.assessment_id}
                    </Link>
                    {inst.occurrence_count > 1 && (
                      <span className="text-xs text-slate-500">×{inst.occurrence_count.toLocaleString()}</span>
                    )}
                    <span className="text-slate-500">{formatDate(inst.observed_at)}</span>
                    {inst.source_severity && <SeverityBadge severity={inst.source_severity} />}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <RemediationSection finding={finding} owners={owners} onChanged={load} />
          <ValidationSection finding={finding} onChanged={load} />
        </div>

        <div className="space-y-4">
          <Card>
            <h2 className="mb-3 text-sm font-semibold text-slate-200">Ownership & Status</h2>
            <label className="mb-3 block">
              <span className="mb-1 block text-xs font-medium text-slate-400">Owner / Team</span>
              <select
                className="select w-full"
                value={finding.owner?.id ?? ''}
                onChange={(e) => handleOwnerChange(e.target.value)}
              >
                <option value="">Unassigned</option>
                {owners.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                    {o.team ? ` (${o.team})` : ''}
                  </option>
                ))}
              </select>
            </label>
            <QuickAddOwner onAdded={loadOwners} />
            <label className="mt-4 block">
              <span className="mb-1 block text-xs font-medium text-slate-400">Status</span>
              <select className="select w-full" value={finding.status} onChange={(e) => handleStatusChange(e.target.value)}>
                {ALL_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {titleCase(s)}
                  </option>
                ))}
              </select>
              <span className="mt-1 block text-[11px] text-slate-500">
                Direct transition to Validated is blocked — record a passing validation below instead.
              </span>
            </label>
          </Card>
        </div>
      </div>
    </div>
  )
}

function QuickAddOwner({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [team, setTeam] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-xs font-medium text-sky-400 hover:underline"
      >
        + New owner / team
      </button>
    )
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setSubmitting(true)
    try {
      await api.createOwner({ name: name.trim(), team: team.trim() || undefined })
      setName('')
      setTeam('')
      setOpen(false)
      onAdded()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={submit} className="mt-2 flex items-center gap-2">
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Owner name"
        className="input"
      />
      <input value={team} onChange={(e) => setTeam(e.target.value)} placeholder="Team (optional)" className="input" />
      <button
        type="submit"
        disabled={submitting}
        className="whitespace-nowrap rounded-md bg-sky-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-400 disabled:opacity-50"
      >
        Add
      </button>
    </form>
  )
}

function Info({ label, value, mono, children }: { label: string; value?: string; mono?: boolean; children?: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className={`mt-0.5 text-slate-200 ${mono ? 'font-mono text-xs' : ''}`}>{children ?? value}</dd>
    </div>
  )
}

function RemediationSection({
  finding,
  owners,
  onChanged,
}: {
  finding: FindingDetailType
  owners: Owner[]
  onChanged: () => void
}) {
  const [notes, setNotes] = useState('')
  const [action, setAction] = useState('')
  const [nextStatus, setNextStatus] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await api.createRemediation({
        finding_id: finding.id,
        recommended_action: action || undefined,
        remediation_notes: notes || undefined,
        status: (nextStatus as FindingStatus) || undefined,
      })
      setNotes('')
      setAction('')
      setNextStatus('')
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to add remediation note.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-slate-200">Remediation</h2>

      {finding.remediations.length > 0 && (
        <ul className="mb-4 space-y-3">
          {finding.remediations.map((r) => (
            <li key={r.id} className="rounded-md border border-slate-800 bg-slate-900/40 p-3 text-sm">
              <div className="mb-1 flex items-center justify-between">
                <StatusBadge status={r.status} />
                <span className="text-xs text-slate-500">{formatDate(r.created_at)}</span>
              </div>
              {r.recommended_action && <p className="text-slate-300">Action: {r.recommended_action}</p>}
              {r.remediation_notes && <p className="mt-1 text-slate-400">{r.remediation_notes}</p>}
              {r.owner_id && (
                <p className="mt-1 text-xs text-slate-500">
                  Owner: {owners.find((o) => o.id === r.owner_id)?.name ?? `#${r.owner_id}`}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={submit} className="space-y-3 border-t border-slate-800 pt-4">
        <input
          value={action}
          onChange={(e) => setAction(e.target.value)}
          placeholder="Recommended action"
          className="input"
        />
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Remediation notes…"
          rows={2}
          className="input"
        />
        <div className="flex items-center gap-3">
          <select className="select" value={nextStatus} onChange={(e) => setNextStatus(e.target.value)}>
            <option value="">Keep current status</option>
            {ALL_STATUSES.filter((s) => s !== 'VALIDATED').map((s) => (
              <option key={s} value={s}>
                Move to {titleCase(s)}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-sky-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-400 disabled:opacity-50"
          >
            {submitting ? 'Saving…' : 'Add Remediation Note'}
          </button>
        </div>
        {error && <ErrorState message={error} />}
      </form>
    </Card>
  )
}

function ValidationSection({ finding, onChanged }: { finding: FindingDetailType; onChanged: () => void }) {
  const [method, setMethod] = useState('')
  const [evidence, setEvidence] = useState('')
  const [validatedBy, setValidatedBy] = useState('')
  const [result, setResult] = useState<'PASS' | 'FAIL' | 'INCONCLUSIVE'>('PASS')
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await api.createValidation({
        finding_id: finding.id,
        validation_method: method || undefined,
        evidence: evidence || undefined,
        validation_date: date,
        result,
        validated_by: validatedBy || undefined,
      })
      setMethod('')
      setEvidence('')
      setValidatedBy('')
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to record validation.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-slate-200">Validation</h2>

      {finding.validations.length > 0 && (
        <ul className="mb-4 space-y-3">
          {finding.validations.map((v) => (
            <li key={v.id} className="rounded-md border border-slate-800 bg-slate-900/40 p-3 text-sm">
              <div className="mb-1 flex items-center justify-between">
                <span
                  className={`text-xs font-semibold ${
                    v.result === 'PASS' ? 'text-emerald-400' : v.result === 'FAIL' ? 'text-red-400' : 'text-amber-400'
                  }`}
                >
                  {v.result}
                </span>
                <span className="text-xs text-slate-500">{formatDate(v.validation_date)}</span>
              </div>
              {v.validation_method && <p className="text-slate-300">Method: {v.validation_method}</p>}
              {v.evidence && <p className="mt-1 text-slate-400">Evidence: {v.evidence}</p>}
              {v.validated_by && <p className="mt-1 text-xs text-slate-500">By {v.validated_by}</p>}
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={submit} className="space-y-3 border-t border-slate-800 pt-4">
        <div className="grid grid-cols-2 gap-3">
          <input value={method} onChange={(e) => setMethod(e.target.value)} placeholder="Validation method" className="input" />
          <input value={validatedBy} onChange={(e) => setValidatedBy(e.target.value)} placeholder="Validated by" className="input" />
        </div>
        <textarea
          value={evidence}
          onChange={(e) => setEvidence(e.target.value)}
          placeholder="Evidence…"
          rows={2}
          className="input"
        />
        <div className="flex items-center gap-3">
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="input w-auto" />
          <select className="select" value={result} onChange={(e) => setResult(e.target.value as never)}>
            <option value="PASS">Pass</option>
            <option value="FAIL">Fail</option>
            <option value="INCONCLUSIVE">Inconclusive</option>
          </select>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-400 disabled:opacity-50"
          >
            {submitting ? 'Saving…' : 'Record Validation'}
          </button>
        </div>
        {error && <ErrorState message={error} />}
      </form>
    </Card>
  )
}
