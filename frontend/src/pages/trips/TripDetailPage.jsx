import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Edit2, Trash2, Plus, MapPin, Clock, Images, Route, Globe, Share2 } from 'lucide-react'
import { tripsApi } from '../../api/trips'
import { timelineApi } from '../../api/timeline'
import { useAuth } from '../../contexts/AuthContext'
import Layout from '../../components/layout/Layout'
import TripMap from '../../components/map/TripMap'
import TimelineView from '../../components/timeline/TimelineView'
import GalleryView from '../../components/gallery/GalleryView'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import Button from '../../components/ui/Button'
import { fmtDateRange } from '../../utils/formatDate'
import { getMethod } from '../../utils/travelIcons'
import toast from 'react-hot-toast'

const TABS = [
  { id: 'map',      label: 'Map',      Icon: MapPin },
  { id: 'timeline', label: 'Timeline', Icon: Clock },
  { id: 'gallery',  label: 'Gallery',  Icon: Images },
  { id: 'routes',   label: 'Routes',   Icon: Route },
]

export default function TripDetailPage() {
  const { tripId } = useParams()
  const navigate   = useNavigate()
  const { user }   = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()

  const [trip, setTrip]         = useState(null)
  const [points, setPoints]     = useState([])
  const [segments, setSegments] = useState([])
  const [loading, setLoading]   = useState(true)
  const [tab, setTab]           = useState(searchParams.get('tab') || 'map')
  const [mapFocusTarget, setMapFocusTarget] = useState(() => {
    const lat = searchParams.get('focusLat')
    const lng = searchParams.get('focusLon')
    if (!lat || !lng) return null
    return {
      lat: Number(lat),
      lng: Number(lng),
      zoom: Number(searchParams.get('focusZoom') || 12),
    }
  })

  const load = async () => {
    try {
      const [t, p, s] = await Promise.all([
        tripsApi.get(tripId),
        timelineApi.listPoints(tripId),
        timelineApi.listSegments(tripId),
      ])
      setTrip(t); setPoints(p); setSegments(s)
    } catch { navigate('/trips') }
    finally   { setLoading(false) }
  }

  useEffect(() => { load() }, [tripId])

  useEffect(() => {
    const nextTab = searchParams.get('tab') || 'map'
    setTab(nextTab)

    const lat = searchParams.get('focusLat')
    const lng = searchParams.get('focusLon')
    if (lat && lng) {
      setMapFocusTarget({
        lat: Number(lat),
        lng: Number(lng),
        zoom: Number(searchParams.get('focusZoom') || 12),
      })
    } else {
      setMapFocusTarget(null)
    }
  }, [searchParams])

  const updateViewParams = (nextTab, focusTarget = null) => {
    const nextParams = new URLSearchParams(searchParams)
    nextParams.set('tab', nextTab)
    if (focusTarget) {
      nextParams.set('focusLat', String(focusTarget.lat))
      nextParams.set('focusLon', String(focusTarget.lng))
      nextParams.set('focusZoom', String(focusTarget.zoom ?? 12))
    } else {
      nextParams.delete('focusLat')
      nextParams.delete('focusLon')
      nextParams.delete('focusZoom')
    }
    setSearchParams(nextParams, { replace: true })
  }

  const handleDeleteTrip = async () => {
    if (!confirm('Delete this trip and all its data?')) return
    await tripsApi.delete(tripId)
    toast.success('Trip deleted')
    navigate('/trips')
  }

  const handleDeletePoint = async (pointId) => {
    if (!confirm('Delete this location?')) return
    await timelineApi.deletePoint(pointId)
    toast.success('Location removed')
    load()
  }

  const handleMapDeletePoint = async (point) => {
    if (!confirm('Delete this location?')) return

    const currentIndex = points.findIndex((item) => item.id === point.id)
    const fallbackPoint = currentIndex > 0
      ? points[currentIndex - 1]
      : (currentIndex >= 0 && currentIndex < points.length - 1 ? points[currentIndex + 1] : null)

    await timelineApi.deletePoint(point.id)
    toast.success('Location removed')
    updateViewParams(
      'map',
      fallbackPoint?.latitude && fallbackPoint?.longitude
        ? {
            lat: Number(fallbackPoint.latitude),
            lng: Number(fallbackPoint.longitude),
            zoom: 9,
          }
        : null
    )
    load()
  }

  const handleMapEditPoint = (point) => {
    navigate(
      `/trips/${tripId}/points/${point.id}/edit?returnTo=map&focusLat=${point.latitude}&focusLon=${point.longitude}&focusZoom=13`
    )
  }

  if (loading) return <Layout><div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div></Layout>
  if (!trip)   return null

  const publicUrl = `${window.location.origin}/u/${user?.username}/trips/${tripId}`

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <Link to="/trips" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-primary-600 mb-3">
            <ArrowLeft className="w-4 h-4" /> My Trips
          </Link>

          <div
            className="relative rounded-2xl overflow-hidden h-52 bg-gradient-to-br from-primary-600 to-sky-500"
            style={trip.cover_image_url ? { backgroundImage: `url(${trip.cover_image_url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : {}}
          >
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
            <div className="absolute bottom-4 left-5 right-5">
              <div className="flex items-end justify-between gap-4">
                <div>
                  <h1 className="text-2xl font-bold text-white">{trip.title}</h1>
                  {(trip.start_date || trip.end_date) && (
                    <p className="text-white/70 text-sm mt-1">{fmtDateRange(trip.start_date, trip.end_date)}</p>
                  )}
                  {trip.stats && (
                    <p className="text-white/60 text-xs mt-1">
                      {trip.stats.total_points} places · {trip.stats.total_countries} {trip.stats.total_countries === 1 ? 'country' : 'countries'}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {trip.visibility === 'public' && (
                    <button
                      onClick={() => { navigator.clipboard.writeText(publicUrl); toast.success('Link copied!') }}
                      className="flex items-center gap-1 bg-white/20 hover:bg-white/30 text-white text-xs px-3 py-1.5 rounded-lg"
                    >
                      <Share2 className="w-3 h-3" /> Share
                    </button>
                  )}
                  <Link to={`/trips/${tripId}/edit`} className="flex items-center gap-1 bg-white/20 hover:bg-white/30 text-white text-xs px-3 py-1.5 rounded-lg">
                    <Edit2 className="w-3 h-3" /> Edit
                  </Link>
                  <button onClick={handleDeleteTrip} className="flex items-center gap-1 bg-red-500/80 hover:bg-red-600 text-white text-xs px-3 py-1.5 rounded-lg">
                    <Trash2 className="w-3 h-3" /> Delete
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex items-center gap-1 bg-white rounded-xl border border-slate-100 shadow-sm p-1">
          {TABS.map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => updateViewParams(id)}
              className={`flex-1 flex items-center justify-center gap-2 py-2 text-sm font-medium rounded-lg transition-colors
                ${tab === id ? 'bg-primary-600 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-50'}`}
            >
              <Icon className="w-4 h-4" /><span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </div>

        {/* Add location button */}
        <div className="flex justify-end">
          <Link
            to={`/trips/${tripId}/points/new?returnTo=${tab}`}
            className="flex items-center gap-2 bg-primary-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Plus className="w-4 h-4" /> Add Location
          </Link>
        </div>

        {/* Tab content */}
        {tab === 'map' && (
          <div className="h-[500px] rounded-xl overflow-hidden border border-slate-100 shadow-sm">
            <TripMap
              points={points}
              segments={segments}
              focusTarget={mapFocusTarget}
              onEditPoint={handleMapEditPoint}
              onDeletePoint={handleMapDeletePoint}
            />
          </div>
        )}

        {tab === 'timeline' && (
          <TimelineView points={points} segments={segments} tripId={tripId} onDelete={handleDeletePoint} />
        )}

        {tab === 'gallery' && (
          <GalleryView points={points} />
        )}

        {tab === 'routes' && (
          <div className="bg-white rounded-xl border border-slate-100 shadow-sm divide-y divide-slate-50">
            {segments.length === 0 ? (
              <div className="py-12 text-center text-slate-400">No routes recorded yet.</div>
            ) : (
              segments.map(seg => {
                const from = points.find(p => p.id === seg.from_point_id)
                const to   = points.find(p => p.id === seg.to_point_id)
                const method = getMethod(seg.travel_method)
                const Icon   = method.Icon
                return (
                  <div key={seg.id} className="flex items-center gap-4 px-5 py-4">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: `${method.color}1a` }}>
                      <Icon className="w-4 h-4" style={{ color: method.color }} />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-slate-700">
                        {from?.place_name || '?'} → {to?.place_name || '?'}
                      </p>
                      <p className="text-xs text-slate-400">{method.label}{seg.description ? ` · ${seg.description}` : ''}</p>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        )}
      </div>
    </Layout>
  )
}
