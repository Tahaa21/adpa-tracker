import { titleCase } from '../utils/format'

const PRIORITY_STYLES: Record<string, string> = {
  P1: 'bg-red-500/15 text-red-400 border-red-500/30',
  P2: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  P3: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  P4: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
}

export function PriorityBadge({ priority }: { priority: string }) {
  const style = PRIORITY_STYLES[priority] ?? 'bg-slate-500/15 text-slate-300 border-slate-500/30'
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold ${style}`}
    >
      {priority}
    </span>
  )
}

const SEVERITY_STYLES: Record<string, string> = {
  critical: 'bg-red-500/15 text-red-400 border-red-500/30',
  high: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  medium: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  low: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
}

export function SeverityBadge({ severity }: { severity: string }) {
  const style = SEVERITY_STYLES[severity?.toLowerCase()] ?? SEVERITY_STYLES.low
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium capitalize ${style}`}
    >
      {severity}
    </span>
  )
}

const STATUS_STYLES: Record<string, string> = {
  OPEN: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
  TRIAGED: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  ASSIGNED: 'bg-indigo-500/15 text-indigo-400 border-indigo-500/30',
  IN_REMEDIATION: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  READY_FOR_VALIDATION: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
  VALIDATED: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  CLOSED: 'bg-slate-600/20 text-slate-400 border-slate-600/30',
  RISK_ACCEPTED: 'bg-teal-500/15 text-teal-400 border-teal-500/30',
  FALSE_POSITIVE: 'bg-slate-600/20 text-slate-400 border-slate-600/30',
  DEFERRED: 'bg-slate-600/20 text-slate-400 border-slate-600/30',
  REOPENED: 'bg-red-500/15 text-red-400 border-red-500/30',
}

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.OPEN
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${style}`}
    >
      {titleCase(status)}
    </span>
  )
}

export function CategoryBadge({ category }: { category: string }) {
  return (
    <span className="inline-flex items-center rounded-md border border-slate-600/40 bg-slate-800/60 px-2 py-0.5 text-xs font-medium text-slate-300">
      {titleCase(category)}
    </span>
  )
}
