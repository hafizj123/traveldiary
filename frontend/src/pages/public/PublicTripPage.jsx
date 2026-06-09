import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Globe, MapPin, Clock, Images, Route } from 'lucide-react'
import { publicApi } from '../../api/public'
import TripMap from '../../components/map/TripMap'
import TimelineView from '../../components/timeline/TimelineView'
import GalleryView from '../../components/gallery/GalleryView'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import { fmtDateRange } from '../../utils/formatDate'
import { getMethod } from '../../utils/travelIcons'

const TABS = [
  { id: 'map',      label: 'Map',      Icon: MapPin },
  { id: 'timeline', label: 'Timeline', Icon: Clock },
  { id: 'gallery',  label: 'Gallery',  Icon: Images },
  { id: 'routes',   label: 'Routes',   Icon: Route },
]

export default function PublicTripPage() {
  const { username, tripId } = useParams()
  const [data, setData]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState('')
  const [tab, setTab]       = useState('map')

  useEffect(() => {
    publicApi.trip(username, tripId)
      .then(setData)
      .catch(() => setError('Trip not found or not public'))
      .finally(() => setLoading(false))
  }, [username, tripId])

  if (loading) return <div className="min-h-screen flex items-center justify-center"><LoadingSpinner size="lg" /></div>

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-100 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex h-16 items-center justify-between">
          <Link to="/" className="flex items-center gap-2 font-bold text-primary-600">
            <Globe className="w-5 h-5" /> Travel Diary
          </Link>
          <Link to={`/u/${username}`} className="text-sm text-slate-500 hover:text-primary-600">
            ← {username}'s trips
          </Link>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {error ? (
          <div className="text-center py-24 text-slate-400">{error}</div>
        ) : data && (
          <>
            {/* Trip header */}
            <div
              className="relative rounded-2xl overflow-hidden h-52 bg-gradient-to-br from-primary-600 to-sky-500"
              style={data.trip.cover_image_url
                ? { backgroundImage: `url(${data.trip.cover_image_url})`, backgroundSize: 'cover', backgroundPosition: 'center' }
                : {}}
            >
              <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
              <div className="absolute bottom-4 left-5">
                <h1 className="text-2xl font-bold text-white">{data.trip.title}</h1>
                <p className="text-white/70 text-sm">{fmtDateRange(data.trip.start_date, data.trip.end_date)}</p>
                <p className="text-white/50 text-xs mt-1">
                  {data.points.length} places · shared by {data.owner}
                </p>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex items-center gap-1 bg-white rounded-xl border border-slate-100 shadow-sm p-1">
              {TABS.map(({ id, label, Icon }) => (
                <button key={id} onClick={() => setTab(id)}
                  className={`flex-1 flex items-center justify-center gap-2 py-2 text-sm font-medium rounded-lg transition-colors
                    ${tab === id ? 'bg-primary-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}>
                  <Icon className="w-4 h-4" /><span className="hidden sm:inline">{label}</span>
                </button>
              ))}
            </div>

            {tab === 'map' && (
              <div className="h-[500px] rounded-xl overflow-hidden border border-slate-100 shadow-sm">
                <TripMap points={data.points} segments={data.segments} />
              </div>
            )}
            {tab === 'timeline' && <TimelineView points={data.points} segments={data.segments} />}
            {tab === 'gallery'  && <GalleryView points={data.points} />}
            {tab === 'routes'   && (
              <div className="bg-white rounded-xl border border-slate-100 shadow-sm divide-y divide-slate-50">
                {data.segments.length === 0
                  ? <div className="py-12 text-center text-slate-400">No routes recorded.</div>
                  : data.segments.map(seg => {
                      const from   = data.points.find(p => p.id === seg.from_point_id)
                      const to     = data.points.find(p => p.id === seg.to_point_id)
                      const method = getMethod(seg.travel_method)
                      const Icon   = method.Icon
                      return (
                        <div key={seg.id} className="flex items-center gap-4 px-5 py-4">
                          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: `${method.color}1a` }}>
                            <Icon className="w-4 h-4" style={{ color: method.color }} />
                          </div>
                          <p className="text-sm font-medium text-slate-700">
                            {from?.place_name} → {to?.place_name}
                            <span className="font-normal text-slate-400 ml-2">({method.label})</span>
                          </p>
                        </div>
                      )
                    })
                }
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
