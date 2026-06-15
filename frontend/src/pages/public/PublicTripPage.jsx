import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Globe, MapPin, Clock, Images, Route, Share2, BookOpen } from 'lucide-react'
import { publicApi } from '../../api/public'
import { useAuth } from '../../contexts/AuthContext'
import Navbar from '../../components/layout/Navbar'
import TripMap from '../../components/map/TripMap'
import TimelineView from '../../components/timeline/TimelineView'
import GalleryView from '../../components/gallery/GalleryView'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import { fmtDateRange } from '../../utils/formatDate'
import { getMethod } from '../../utils/travelIcons'

const TABS = [
  { id: 'map', label: 'Map', Icon: MapPin },
  { id: 'timeline', label: 'Timeline', Icon: Clock },
  { id: 'gallery', label: 'Gallery', Icon: Images },
  { id: 'routes', label: 'Routes', Icon: Route },
]

export default function PublicTripPage() {
  const { user } = useAuth()
  const { username, tripId, shareSlug } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('map')

  useEffect(() => {
    setLoading(true)
    setError('')
    const loader = shareSlug ? publicApi.sharedTrip(shareSlug) : publicApi.trip(username, tripId)
    loader
      .then(setData)
      .catch(() => setError('Trip not found or not shared'))
      .finally(() => setLoading(false))
  }, [shareSlug, username, tripId])

  if (loading) return <div className="min-h-screen flex items-center justify-center"><LoadingSpinner size="lg" /></div>

  return (
    <div className="min-h-screen bg-slate-50">
      {user ? (
        <Navbar />
      ) : (
        <header className="sticky top-0 z-50 border-b border-slate-100 bg-white">
          <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
            <Link to="/" className="flex items-center gap-2 font-bold text-primary-600">
              <Globe className="w-5 h-5" /> Travel Diary
            </Link>
            <div className="flex items-center gap-3">
              {data?.owner ? (
                <Link to={`/u/${data.owner}`} className="text-sm text-slate-500 hover:text-primary-600">
                  View {data.owner}'s trips
                </Link>
              ) : null}
              <Link to="/shared-trips" className="text-sm font-medium text-primary-600 hover:underline">
                Shared Trips
              </Link>
            </div>
          </div>
        </header>
      )}

      <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        {error ? (
          <div className="text-center py-24 text-slate-400">{error}</div>
        ) : data && (
          <>
            {user && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
                {data?.owner ? (
                  <Link to={`/u/${data.owner}`} className="text-sm font-medium text-slate-600 hover:text-primary-600">
                    View {data.owner}'s trips
                  </Link>
                ) : <span />}
                <Link to="/shared-trips" className="text-sm font-medium text-primary-600 hover:underline">
                  Shared Trips
                </Link>
              </div>
            )}
            <div
              className="relative rounded-2xl overflow-hidden h-52 bg-gradient-to-br from-primary-600 to-sky-500"
              style={data.trip.cover_image_url
                ? { backgroundImage: `url(${data.trip.cover_image_url})`, backgroundSize: 'cover', backgroundPosition: 'center' }
                : {}}
            >
              <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(window.location.href)}
                className="absolute right-5 top-5 inline-flex items-center gap-1 rounded-lg bg-white/20 px-3 py-1.5 text-xs text-white hover:bg-white/30"
              >
                <Share2 className="w-3 h-3" />
                Copy link
              </button>
              <div className="absolute bottom-4 left-5 right-5">
                <h1 className="text-2xl font-bold text-white">{data.trip.title}</h1>
                <p className="text-white/70 text-sm">{fmtDateRange(data.trip.start_date, data.trip.end_date)}</p>
                <p className="text-white/50 text-xs mt-1">
                  {data.points.length} places | shared by {data.owner}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-white/70">
                  <span>{data.trip.public_stats?.unique_views_total || 0} unique views</span>
                  <span>{data.trip.visibility === 'unlisted' ? 'Unlisted link' : 'Public trip'}</span>
                </div>
              </div>
            </div>

            {data.trip.description ? (
              <div className="rounded-2xl border border-slate-100 bg-white px-5 py-4 text-sm text-slate-600 shadow-sm">
                {data.trip.description}
              </div>
            ) : null}

            {data.trip.journal_exists ? (
              <div className="rounded-2xl border border-slate-100 bg-white px-5 py-4 shadow-sm">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-slate-800">Travel Journal</p>
                    <p className="mt-1 text-sm text-slate-500">Read the story version of this trip when a journal has been generated.</p>
                  </div>
                  <Link
                    to={shareSlug ? `/shared/${shareSlug}/journal` : `/u/${username}/trips/${tripId}/journal`}
                    className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
                  >
                    <BookOpen className="h-4 w-4" />
                    Open journal
                  </Link>
                </div>
              </div>
            ) : null}

            <div className="flex items-center gap-1 bg-white rounded-xl border border-slate-100 shadow-sm p-1">
              {TABS.map(({ id, label, Icon }) => (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`flex-1 flex items-center justify-center gap-2 py-2 text-sm font-medium rounded-lg transition-colors ${
                    tab === id ? 'bg-primary-600 text-white' : 'text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span className="hidden sm:inline">{label}</span>
                </button>
              ))}
            </div>

            {tab === 'map' && (
              <div className="h-[500px] rounded-xl overflow-hidden border border-slate-100 shadow-sm">
                <TripMap points={data.points} segments={data.segments} />
              </div>
            )}
            {tab === 'timeline' && <TimelineView points={data.points} segments={data.segments} />}
            {tab === 'gallery' && <GalleryView points={data.points} />}
            {tab === 'routes' && (
              <div className="bg-white rounded-xl border border-slate-100 shadow-sm divide-y divide-slate-50">
                {data.segments.length === 0
                  ? <div className="py-12 text-center text-slate-400">No routes recorded.</div>
                  : data.segments.map((seg) => {
                      const from = data.points.find((p) => p.id === seg.from_point_id)
                      const to = data.points.find((p) => p.id === seg.to_point_id)
                      const method = getMethod(seg.travel_method)
                      const Icon = method.Icon
                      return (
                        <div key={seg.id} className="flex items-center gap-4 px-5 py-4">
                          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: `${method.color}1a` }}>
                            <Icon className="w-4 h-4" style={{ color: method.color }} />
                          </div>
                          <p className="text-sm font-medium text-slate-700">
                            {from?.place_name} {'->'} {to?.place_name}
                            <span className="font-normal text-slate-400 ml-2">({method.label})</span>
                          </p>
                        </div>
                      )
                    })}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
