import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { FindingListItem, Owner } from '../api/types'
import { CategoryBadge, PriorityBadge, SeverityBadge, StatusBadge } from '../components/Badges'
import { Card, EmptyState, ErrorState, LoadingState, PageHeader } from '../components/Card'
import { ALL_STATUSES } from '../api/types'
import { formatDate, titleCase } from '../utils/format'

const CATEGORIES = [
  'TIER_0',
  'IDENTITY_EXPOSURE',
  'ACCOUNT_HYGIENE',
  'POLICY_CONFIGURATION',
  'PRIVILEGE',
  'CREDENTIAL_EXPOSURE',
  'DELEGATION',
  'TRUST',
  'OTHER',
]
const SEVERITIES = ['critical', 'high', 'medium', 'low']

export default function Findings() {
  const [findings, setFindings] = useState<FindingListItem[] | null>(null)
  const [owners, setOwners] = useState<Owner[]>([])
  const [error, setError] = useState<string | null>(null)

  const [search, setSearch] = useState('')
  const [priority, setPriority] = useState('')
  const [status, setStatus] = useState('')
  const [category, setCategory] = useState('')
  const [severity, setSeverity] = useState('')
  const [ownerId, setOwnerId] = useState('')

  useEffect(() => {
    api.listOwners().then(setOwners).catch(() => {})
  }, [])

  useEffect(() => {
    const handle = setTimeout(() => {
      api
        .listFindings({
          search: search || undefined,
          priority: (priority as never) || undefined,
          status: (status as never) || undefined,
          category: category || undefined,
          severity: severity || undefined,
          owner_id: ownerId ? Number(ownerId) : undefined,
        })
        .then(setFindings)
        .catch((e) => setError(e.message))
    }, 250)
    return () => clearTimeout(handle)
  }, [search, priority, status, category, severity, ownerId])

  const ownerMap = useMemo(() => new Map(owners.map((o) => [o.id, o])), [owners])

  return (
    <div>
      <PageHeader title="Findings" subtitle="Search and filter normalized findings across every imported assessment." />

      <Card className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title or asset…"
            className="input max-w-xs"
          />
          <select className="select" value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="">All Priorities</option>
            <option value="P1">P1</option>
            <option value="P2">P2</option>
            <option value="P3">P3</option>
          </select>
          <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All Statuses</option>
            {ALL_STATUSES.map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </select>
          <select className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All Categories</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {titleCase(c)}
              </option>
            ))}
          </select>
          <select className="select" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">All Severities</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </select>
          <select className="select" value={ownerId} onChange={(e) => setOwnerId(e.target.value)}>
            <option value="">All Owners</option>
            {owners.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
          {findings && <span className="ml-auto text-xs text-slate-500">{findings.length} findings</span>}
        </div>
      </Card>

      {error && <ErrorState message={error} />}
      {!findings && !error && <LoadingState />}
      {findings && findings.length === 0 && <EmptyState message="No findings match your filters." />}

      {findings && findings.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[1100px] text-left text-sm">
            <thead className="border-b border-slate-800 text-xs text-slate-500 uppercase">
              <tr>
                <th className="px-4 py-3 font-medium">Priority</th>
                <th className="px-4 py-3 font-medium">Risk</th>
                <th className="px-4 py-3 font-medium">Finding</th>
                <th className="px-4 py-3 font-medium">Category</th>
                <th className="px-4 py-3 font-medium">Affected Asset</th>
                <th className="px-4 py-3 font-medium">Severity</th>
                <th className="px-4 py-3 font-medium">Owner</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">First Seen</th>
                <th className="px-4 py-3 font-medium">Last Seen</th>
              </tr>
            </thead>
            <tbody>
              {findings.map((f) => (
                <tr
                  key={f.id}
                  className={`cursor-pointer border-b border-slate-800/60 last:border-0 hover:bg-slate-800/30 ${
                    !f.currently_present ? 'opacity-50' : ''
                  }`}
                >
                  <td className="px-4 py-3">
                    <PriorityBadge priority={f.priority} />
                  </td>
                  <td className="px-4 py-3 font-mono text-slate-300">{f.risk_score}</td>
                  <td className="px-4 py-3">
                    <Link to={`/findings/${f.id}`} className="font-medium text-sky-400 hover:underline">
                      {f.title}
                    </Link>
                    {!f.currently_present && <div className="text-[11px] text-slate-500">No longer observed</div>}
                  </td>
                  <td className="px-4 py-3">
                    <CategoryBadge category={f.category} />
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {f.asset.name}
                    <div className="text-[11px] text-slate-500">{f.asset.domain}</div>
                  </td>
                  <td className="px-4 py-3">
                    <SeverityBadge severity={f.severity} />
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {f.owner ? ownerMap.get(f.owner.id)?.name ?? f.owner.name : <span className="text-slate-600">Unassigned</span>}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={f.status} />
                  </td>
                  <td className="px-4 py-3 text-slate-500">{formatDate(f.first_seen)}</td>
                  <td className="px-4 py-3 text-slate-500">{formatDate(f.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
