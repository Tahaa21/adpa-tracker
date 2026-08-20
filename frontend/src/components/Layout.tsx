import { NavLink, Outlet } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: '📊', end: true },
  { to: '/assessments', label: 'Assessments', icon: '📥', end: false },
  { to: '/findings', label: 'Findings', icon: '🛡️', end: false },
]

export default function Layout() {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#0b1220] text-slate-100">
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-800 bg-[#0d1526]">
        <div className="flex items-center gap-2 border-b border-slate-800 px-5 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-sky-500/20 text-sky-400">
            🛡️
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold text-slate-100">AD Sec Tracker</div>
            <div className="text-[11px] text-slate-500">Remediation Ops</div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 px-3 py-4">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-sky-500/10 text-sky-300'
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                }`
              }
            >
              <span className="text-base leading-none">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-800 px-4 py-4 text-[11px] text-slate-500">
          <p>Pentera-first MVP.</p>
          <p>Not an attack-path graph.</p>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1400px] px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
