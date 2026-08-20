import type { ReactNode } from 'react'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-xl border border-slate-800 bg-[#101a2e] p-5 shadow-sm shadow-black/20 ${className}`}
    >
      {children}
    </div>
  )
}

export function StatCard({
  label,
  value,
  sub,
  accent = 'slate',
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  accent?: 'slate' | 'red' | 'amber' | 'emerald' | 'sky'
}) {
  const accentColor: Record<string, string> = {
    slate: 'text-slate-100',
    red: 'text-red-400',
    amber: 'text-amber-400',
    emerald: 'text-emerald-400',
    sky: 'text-sky-400',
  }
  return (
    <Card>
      <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">{label}</div>
      <div className={`mt-2 text-3xl font-semibold ${accentColor[accent]}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </Card>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-slate-100">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
      </div>
      {actions}
    </div>
  )
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return <div className="py-16 text-center text-sm text-slate-500">{label}</div>
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
      {message}
    </div>
  )
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-700 px-4 py-10 text-center text-sm text-slate-500">
      {message}
    </div>
  )
}
