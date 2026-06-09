import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Globe } from 'lucide-react'
import { tripsApi } from '../../api/trips'
import Layout from '../../components/layout/Layout'
import TripCard from '../../components/trips/TripCard'
import LoadingSpinner from '../../components/ui/LoadingSpinner'

export default function TripsPage() {
  const [trips, setTrips]   = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    tripsApi.list().then(setTrips).finally(() => setLoading(false))
  }, [])

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-slate-800">My Trips</h1>
          <Link
            to="/trips/new"
            className="flex items-center gap-2 bg-primary-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Plus className="w-4 h-4" /> New Trip
          </Link>
        </div>

        {loading ? (
          <div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div>
        ) : trips.length === 0 ? (
          <div className="text-center py-24 bg-white rounded-xl border border-slate-100">
            <Globe className="w-14 h-14 text-slate-200 mx-auto mb-4" />
            <h2 className="font-semibold text-slate-600 mb-2">No trips yet</h2>
            <p className="text-slate-400 text-sm mb-6">Start documenting your travels</p>
            <Link
              to="/trips/new"
              className="inline-flex items-center gap-2 bg-primary-600 text-white text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-primary-700 transition-colors"
            >
              <Plus className="w-4 h-4" /> Create your first trip
            </Link>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {trips.map(t => <TripCard key={t.id} trip={t} />)}
          </div>
        )}
      </div>
    </Layout>
  )
}
