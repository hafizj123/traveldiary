import { Link, useNavigate, useLocation } from 'react-router-dom'
import {
  Globe, LayoutDashboard, Map, LogOut, Menu, X, User,
} from 'lucide-react'
import { useState } from 'react'
import { useAuth } from '../../contexts/AuthContext'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { to: '/trips',     label: 'My Trips',  Icon: Map },
]

export default function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <Link to="/dashboard" className="flex items-center gap-2 font-bold text-primary-600 text-lg">
            <Globe className="w-6 h-6" />
            Travel Diary
          </Link>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-1">
            {NAV.map(({ to, label, Icon }) => (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors
                  ${location.pathname.startsWith(to)
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-slate-600 hover:bg-slate-100'}`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            ))}
          </nav>

          {/* User menu */}
          <div className="hidden md:flex items-center gap-3">
            <span className="text-sm text-slate-500 flex items-center gap-1">
              <User className="w-4 h-4" />
              {user?.username || user?.email}
            </span>
            <button
              onClick={handleLogout}
              className="flex items-center gap-1 text-sm text-slate-500 hover:text-red-500 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              Logout
            </button>
          </div>

          {/* Mobile toggle */}
          <button className="md:hidden p-2" onClick={() => setOpen(!open)}>
            {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {open && (
        <div className="md:hidden border-t border-slate-100 bg-white px-4 pb-4 pt-2 space-y-1">
          {NAV.map(({ to, label, Icon }) => (
            <Link
              key={to}
              to={to}
              onClick={() => setOpen(false)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium
                ${location.pathname.startsWith(to)
                  ? 'bg-primary-50 text-primary-700'
                  : 'text-slate-600 hover:bg-slate-100'}`}
            >
              <Icon className="w-4 h-4" /> {label}
            </Link>
          ))}
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-red-500 w-full"
          >
            <LogOut className="w-4 h-4" /> Logout
          </button>
        </div>
      )}
    </header>
  )
}
