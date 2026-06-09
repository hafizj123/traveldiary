import { useState, useEffect } from 'react'
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
    <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 flex items-center gap-4">
      <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${color}`}>
        <Icon className="w-6 h-6 text-white" />
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-800">{value}</p>
        <p className="text-sm text-slate-500">{label}</p>
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const { user }       = useAuth()
  const [trips, setTrips]   = useState([])
  const [allPoints, setAllPoints] = useState([])
  const [loading, setLoading]   = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const t = await tripsApi.list()
        setTrips(t)
        const points = await Promise.all(t.map(trip => timelineApi.listPoints(trip.id)))
        setAllPoints(points.flat())
      } catch {}
      finally { setLoading(false) }
    }
    load()
  }, [])

  const countries = new Set(allPoints.map(p => p.country)).size
  const photos    = allPoints.filter(p => p.image_url).length

  if (loading) return (
    <Layout>
      <div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div>
    </Layout>
  )

  return (
    <Layout>
      <div className="space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">
              Welcome back, {user?.username || user?.email?.split('@')[0]} 👋
            </h1>
            <p className="text-slate-500 text-sm mt-1">Here's your travel overview</p>
          </div>
          <Link to="/trips/new" className="flex items-center gap-2 bg-primary-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors">
            <Plus className="w-4 h-4" /> New Trip
          </Link>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard value={trips.length}        label="Trips created"    Icon={Map}     color="bg-primary-500" />
          <StatCard value={countries}           label="Countries visited" Icon={Globe}   color="bg-sky-500" />
          <StatCard value={allPoints.length}    label="Places visited"   Icon={MapPin}  color="bg-emerald-500" />
          <StatCard value={photos}              label="Photos uploaded"  Icon={Camera}  color="bg-amber-500" />
        </div>

        {/* World map */}
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-50">
            <h2 className="font-semibold text-slate-800">Your world map</h2>
          </div>
          <div className="h-72">
            <MiniMap points={allPoints} trips={trips} />
          </div>
        </div>

        {/* Recent trips */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-slate-800">Recent trips</h2>
            <Link to="/trips" className="text-sm text-primary-600 hover:underline">View all</Link>
          </div>
          {trips.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-xl border border-slate-100">
              <Globe className="w-12 h-12 text-slate-200 mx-auto mb-3" />
              <p className="text-slate-400">No trips yet.</p>
              <Link to="/trips/new" className="mt-3 inline-block text-sm text-primary-600 hover:underline">
                Create your first trip →
              </Link>
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {trips.slice(0, 8).map(t => <TripCard key={t.id} trip={t} />)}
            </div>
          )}
        </div>
      </div>
    </Layout>
  )
}
