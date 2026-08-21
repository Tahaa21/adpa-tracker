import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { Assessment, ImportSummary } from '../api/types'
import { Card, EmptyState, ErrorState, LoadingState, PageHeader } from '../components/Card'
import { formatDate, formatDateTime } from '../utils/format'

export default function Assessments() {
  const [assessments, setAssessments] = useState<Assessment[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [lastSummary, setLastSummary] = useState<ImportSummary | null>(null)

  function refresh() {
    api
      .listAssessments()
      .then(setAssessments)
      .catch((e) => setError(e.message))
  }

  useEffect(refresh, [])

  return (
    <div>
      <PageHeader
        title="Assessments"
        subtitle="Each import is one Pentera assessment run against your AD environment."
        actions={
          <button
            onClick={() => {
              setShowForm((s) => !s)
              setLastSummary(null)
            }}
            className="rounded-md bg-sky-500 px-4 py-2 text-sm font-medium text-white hover:bg-sky-400"
          >
            {showForm ? 'Cancel' : '+ New Assessment'}
          </button>
        }
      />

      {showForm && (
        <div className="mb-6">
          <NewAssessmentForm
            onImported={(summary) => {
              setLastSummary(summary)
              setShowForm(false)
              refresh()
            }}
          />
        </div>
      )}

      {lastSummary && <ImportSummaryCard summary={lastSummary} />}

      {error && <ErrorState message={error} />}
      {!assessments && !error && <LoadingState />}
      {assessments && assessments.length === 0 && (
        <EmptyState message="No assessments yet. Click “New Assessment” to upload your first Pentera JSON or CSV export." />
      )}

      {assessments && assessments.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-slate-800 text-xs text-slate-500 uppercase">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Source</th>
                <th className="px-4 py-3 font-medium">Assessment Date</th>
                <th className="px-4 py-3 font-medium">Imported</th>
                <th className="px-4 py-3 font-medium">Rows</th>
                <th className="px-4 py-3 font-medium">Risk Score</th>
              </tr>
            </thead>
            <tbody>
              {assessments.map((a) => (
                <tr key={a.id} className="border-b border-slate-800/60 last:border-0 hover:bg-slate-800/30">
                  <td className="px-4 py-3">
                    <Link to={`/assessments/${a.id}`} className="font-medium text-sky-400 hover:underline">
                      {a.name}
                    </Link>
                    {a.environment && <div className="text-xs text-slate-500">{a.environment}</div>}
                  </td>
                  <td className="px-4 py-3 text-slate-300 capitalize">{a.source}</td>
                  <td className="px-4 py-3 text-slate-300">{formatDate(a.assessment_date)}</td>
                  <td className="px-4 py-3 text-slate-500">{formatDateTime(a.imported_at)}</td>
                  <td className="px-4 py-3 text-slate-300">
                    {a.rows_imported}/{a.rows_processed}
                    {a.rows_skipped > 0 && <span className="ml-1 text-amber-400">({a.rows_skipped} skipped)</span>}
                  </td>
                  <td className="px-4 py-3 font-semibold text-slate-100">{a.risk_score ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}

function ImportSummaryCard({ summary }: { summary: ImportSummary }) {
  return (
    <Card className="mb-6 border-emerald-500/30 bg-emerald-500/5">
      <h3 className="mb-3 text-sm font-semibold text-emerald-300">Import complete</h3>
      <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-7">
        <Stat label="Records Discovered" value={summary.rows_processed} />
        <Stat label="Imported" value={summary.rows_imported} />
        <Stat label="Skipped" value={summary.rows_skipped} />
        <Stat label="Unknown Mappings" value={summary.unknown_mappings} />
        <Stat label="Duplicates Coalesced" value={summary.duplicate_observations_coalesced} />
        <Stat label="New" value={summary.new_findings} />
        <Stat label="Recurring" value={summary.recurring_findings} />
      </div>
      {summary.warnings.length > 0 && (
        <div className="mt-4">
          <div className="text-xs font-medium text-amber-400">Warnings ({summary.warnings.length})</div>
          <ul className="mt-1 max-h-40 overflow-y-auto text-xs text-slate-400">
            {summary.warnings.map((w, i) => (
              <li key={i} className="border-t border-slate-800/60 py-1 first:border-0">
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}
      <Link to={`/assessments/${summary.assessment_id}`} className="mt-4 inline-block text-sm text-sky-400 hover:underline">
        View assessment detail →
      </Link>
    </Card>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold text-slate-100">{value}</div>
    </div>
  )
}

function NewAssessmentForm({ onImported }: { onImported: (s: ImportSummary) => void }) {
  const [name, setName] = useState('')
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [environment, setEnvironment] = useState('')
  const [notes, setNotes] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!file) {
      setError('Select a Pentera JSON or CSV file to upload.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const form = new FormData()
      form.set('name', name)
      form.set('assessment_date', date)
      if (environment) form.set('environment', environment)
      if (notes) form.set('notes', notes)
      form.set('file', file)
      const summary = await api.importPentera(form)
      onImported(summary)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Import failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card>
      <h3 className="mb-4 text-sm font-semibold text-slate-200">New Assessment — Pentera JSON or CSV Upload</h3>
      <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Field label="Assessment Name" required>
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Q3 AD Assessment"
            className="input"
          />
        </Field>
        <Field label="Assessment Date" required>
          <input
            required
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="input"
          />
        </Field>
        <Field label="Environment / Domain">
          <input
            value={environment}
            onChange={(e) => setEnvironment(e.target.value)}
            placeholder="e.g. fabrikam.local"
            className="input"
          />
        </Field>
        <Field label="Notes">
          <input value={notes} onChange={(e) => setNotes(e.target.value)} className="input" />
        </Field>
        <div className="md:col-span-2">
          <Field label="Pentera JSON or CSV" required>
            <input
              required
              type="file"
              accept=".json,.csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-300 file:mr-4 file:rounded-md file:border-0 file:bg-slate-700 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-slate-200 hover:file:bg-slate-600"
            />
            <span className="mt-1 block text-xs text-slate-500">
              JSON is preferred. CSV is also supported. PDF is not yet supported.
            </span>
          </Field>
        </div>

        {error && (
          <div className="md:col-span-2">
            <ErrorState message={error} />
          </div>
        )}

        <div className="md:col-span-2">
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-sky-500 px-4 py-2 text-sm font-medium text-white hover:bg-sky-400 disabled:opacity-50"
          >
            {submitting ? 'Importing…' : 'Import Assessment'}
          </button>
        </div>
      </form>
    </Card>
  )
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-400">
        {label} {required && <span className="text-red-400">*</span>}
      </span>
      {children}
    </label>
  )
}
