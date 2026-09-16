import type { ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: '📊' },
  { to: '/catalog', label: 'Brands & SKUs', icon: '📦' },
  { to: '/warehouses', label: 'Warehouses & Stock', icon: '🏬' },
  { to: '/purchase-orders', label: 'Purchase Orders', icon: '🧾' },
  { to: '/shops', label: 'Shops', icon: '🏪' },
  { to: '/sales-orders', label: 'Sales Orders', icon: '🚚' },
]

export default function Layout({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex">
      <aside className="w-64 bg-brand-900 text-white flex flex-col shrink-0">
        <div className="px-5 py-5 border-b border-white/10">
          <div className="text-lg font-semibold leading-tight">Mumtaz &amp; Co</div>
          <div className="text-xs text-white/60">Distribution ERP &middot; POC</div>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive ? 'bg-white/15 text-white' : 'text-white/70 hover:bg-white/10 hover:text-white'
                }`
              }
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-4 border-t border-white/10 text-xs text-white/50">
          Mumtaz &amp; Co ERP &mdash; proof of concept
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6 shrink-0">
          <div className="text-sm text-slate-500">Sargodha &middot; PTC Distribution</div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-sm font-medium">{me?.first_name} {me?.last_name || me?.username}</div>
              <div className="text-xs text-slate-500">{me?.roles.join(', ') || (me?.is_superuser ? 'Owner' : '')}</div>
            </div>
            <button className="btn-secondary" onClick={handleLogout}>
              Log out
            </button>
          </div>
        </header>
        <main className="flex-1 p-6 overflow-auto">{children}</main>
      </div>
    </div>
  )
}
