import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Globe, MapPin, Camera, Map, Plus } from 'lucide-react'
import { tripsApi } from '../api/trips'
import { timelineApi } from '../api/timeline'
import { useAuth } from '../contexts/AuthContext'
import Layout from '../components/layout/Layout'
import TripCard from '../components/trips/TripCard'
import MiniMap from '../components/map/MiniMap'
import LoadingSpinner from '../components/ui/LoadingSpinner'

function StatCard({ value, label, Icon, color }) {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-slate-100 bg-white p-5 shadow-sm">
      <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${color}`}>
        <Icon className="h-6 w-6 text-white" />
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-800">{value}</p>
        <p className="text-sm text-slate-500">{label}</p>
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const { user } = useAuth()
  const [trips, setTrips] = useState([])
  const [allPoints, setAllPoints] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const t = await tripsApi.list()
        setTrips(t)
        const points = await Promise.all(t.map((trip) => timelineApi.listPoints(trip.id)))
        setAllPoints(points.flat())
      } catch {}
      finally { setLoading(false) }
    }
    load()
  }, [])

  const countries = new Set(allPoints.map((p) => p.country)).size
  const photos = allPoints.filter((p) => p.image_url).length
  const latestTrips = useMemo(() => (
    [...trips].sort((a, b) => {
      const aDate = new Date(a.updated_at || a.created_at || a.start_date || 0).getTime()
      const bDate = new Date(b.updated_at || b.created_at || b.start_date || 0).getTime()
      return bDate - aDate
    }).slice(0, 2)
  ), [trips])

  if (loading) {
    return (
      <Layout>
        <div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div>
      </Layout>
    )
  }

  return (
    <Layout>
      <div className="space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">
              Welcome back, {user?.username || user?.email?.split('@')[0]}
            </h1>
            <p className="mt-1 text-sm text-slate-500">Here&apos;s your travel overview</p>
          </div>
          <Link to="/trips/new" className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700">
            <Plus className="h-4 w-4" /> New Trip
          </Link>
        </div>

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard value={trips.length} label="Trips created" Icon={Map} color="bg-primary-500" />
          <StatCard value={countries} label="Countries visited" Icon={Globe} color="bg-sky-500" />
          <StatCard value={allPoints.length} label="Places visited" Icon={MapPin} color="bg-emerald-500" />
          <StatCard value={photos} label="Photos uploaded" Icon={Camera} color="bg-amber-500" />
        </div>

        <div className="grid gap-5 xl:grid-cols-2 xl:items-stretch">
          <div className="overflow-hidden rounded-xl border border-slate-100 bg-white shadow-sm">
            <div className="border-b border-slate-50 px-5 py-4">
              <h2 className="font-semibold text-slate-800">Your world map</h2>
            </div>
            <div className="h-[48vh] min-h-[320px] xl:h-[calc(100vh-18rem)]">
              <MiniMap points={allPoints} trips={trips} />
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-slate-100 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-50 px-5 py-4">
              <h2 className="font-semibold text-slate-800">Recent trips</h2>
              <Link to="/trips" className="text-sm text-primary-600 hover:underline">View all</Link>
            </div>
            {trips.length === 0 ? (
              <div className="flex h-[48vh] min-h-[320px] flex-col items-center justify-center px-6 text-center xl:h-[calc(100vh-18rem)]">
                <Globe className="mb-3 h-12 w-12 text-slate-200" />
                <p className="text-slate-400">No trips yet.</p>
                <Link to="/trips/new" className="mt-3 inline-block text-sm text-primary-600 hover:underline">
                  Create your first trip {'\u2192'}
                </Link>
              </div>
            ) : (
              <div className="grid h-[48vh] min-h-[320px] auto-rows-min gap-4 overflow-y-auto p-5 xl:h-[calc(100vh-18rem)]">
                {latestTrips.map((trip) => <TripCard key={trip.id} trip={trip} />)}
              </div>
            )}
          </div>
        </div>
      </div>
    </Layout>
  )
}
