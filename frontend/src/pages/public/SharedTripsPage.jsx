import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Compass, Globe, TrendingUp, Clock } from 'lucide-react'

import { publicApi } from '../../api/public'
import { useAuth } from '../../contexts/AuthContext'
import TripCard from '../../components/trips/TripCard'
import LoadingSpinner from '../../components/ui/LoadingSpinner'

const SORTS = [
  { id: 'popular', label: 'Popular', Icon: TrendingUp },
  { id: 'recent', label: 'Recent', Icon: Clock },
]

export default function SharedTripsPage() {
  const { user } = useAuth()
  const [sort, setSort] = useState('popular')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    setError('')
    publicApi.sharedTrips({ sort, limit: 24 })
      .then((data) => setItems(data.items || []))
      .catch(() => setError('Shared trips could not be loaded right now.'))
      .finally(() => setLoading(false))
  }, [sort])

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-100 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex h-16 items-center justify-between">
          <Link to={user ? '/dashboard' : '/'} className="flex items-center gap-2 font-bold text-primary-600">
            <Globe className="w-5 h-5" /> Travel Diary
          </Link>
          <div className="flex items-center gap-3">
            {user ? (
              <>
                <Link to="/trips" className="text-sm font-medium text-slate-600 hover:text-primary-600">My Trips</Link>
                <Link to="/dashboard" className="bg-primary-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors">
                  Dashboard
                </Link>
              </>
            ) : (
              <>
                <Link to="/login" className="text-sm font-medium text-slate-600 hover:text-primary-600">Sign in</Link>
                <Link to="/register" className="bg-primary-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors">
                  Get started
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
        <div className="rounded-3xl bg-gradient-to-br from-sky-600 via-primary-700 to-slate-900 px-6 py-8 text-white shadow-lg">
          <div className="max-w-2xl space-y-3">
            <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-sm">
              <Compass className="w-4 h-4" />
              Shared trips from the community
            </div>
            <h1 className="text-3xl font-bold">Explore journeys other travelers decided to share</h1>
            <p className="text-sm text-white/80">
              Browse by popularity or recency, then open any shared trip without logging in.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm w-full sm:w-fit">
          {SORTS.map(({ id, label, Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setSort(id)}
              className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-colors ${
                sort === id ? 'bg-primary-600 text-white' : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div>
        ) : error ? (
          <div className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
        ) : items.length === 0 ? (
          <div className="rounded-2xl border border-slate-100 bg-white px-6 py-16 text-center text-slate-400">
            No shared trips are visible yet.
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {items.map((trip) => (
              <TripCard key={trip.id} trip={trip} to={`/shared/${trip.share_slug}`} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
