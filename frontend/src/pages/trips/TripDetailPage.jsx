import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Edit2, Trash2, Plus, MapPin, Clock, Images, Route, Share2, BookOpen } from 'lucide-react'
import { tripsApi } from '../../api/trips'
import { timelineApi } from '../../api/timeline'
import Layout from '../../components/layout/Layout'
import TripMap from '../../components/map/TripMap'
import TimelineView from '../../components/timeline/TimelineView'
import GalleryView from '../../components/gallery/GalleryView'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import { fmtDateRange } from '../../utils/formatDate'
import { getMethod } from '../../utils/travelIcons'
import { buildShareUrlFromSlug } from '../../utils/share'
import toast from 'react-hot-toast'

const TABS = [
  { id: 'map', label: 'Map', Icon: MapPin },
  { id: 'timeline', label: 'Timeline', Icon: Clock },
  { id: 'gallery', label: 'Gallery', Icon: Images },
  { id: 'routes', label: 'Routes', Icon: Route },
]

export default function TripDetailPage() {
  const { tripId } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [trip, setTrip] = useState(null)
  const [points, setPoints] = useState([])
  const [segments, setSegments] = useState([])
  const [loading, setLoading] = useState(true)
  const [deletingLocation, setDeletingLocation] = useState(false)
  const [reorderingLocations, setReorderingLocations] = useState(false)
  const [routeNoticeVisible, setRouteNoticeVisible] = useState(searchParams.get('routeNotice') === '1')
  const [tab, setTab] = useState(searchParams.get('tab') || 'map')
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

  const load = async ({ showLoading = false } = {}) => {
    if (showLoading) setLoading(true)
    try {
      const [t, p, s] = await Promise.all([
        tripsApi.get(tripId),
        timelineApi.listPoints(tripId),
        timelineApi.listSegments(tripId),
      ])
      setTrip(t)
      setPoints(p)
      setSegments(s)
    } catch {
      navigate('/trips')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [tripId])

  useEffect(() => {
    const nextTab = searchParams.get('tab') || 'map'
    setTab(nextTab)
    setRouteNoticeVisible(searchParams.get('routeNotice') === '1')

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

  const showRouteNotice = () => {
    setRouteNoticeVisible(true)
    const nextParams = new URLSearchParams(window.location.search)
    nextParams.set('routeNotice', '1')
    setSearchParams(nextParams, { replace: true })
  }

  const dismissRouteNotice = () => {
    setRouteNoticeVisible(false)
    const nextParams = new URLSearchParams(window.location.search)
    nextParams.delete('routeNotice')
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
    setDeletingLocation(true)
    try {
      await timelineApi.deletePoint(pointId)
      await load()
      showRouteNotice()
      toast.success('Location removed')
    } finally {
      setDeletingLocation(false)
    }
  }

  const handleMapDeletePoint = async (point) => {
    if (!confirm('Delete this location?')) return

    const currentIndex = points.findIndex((item) => item.id === point.id)
    const fallbackPoint = currentIndex > 0
      ? points[currentIndex - 1]
      : (currentIndex >= 0 && currentIndex < points.length - 1 ? points[currentIndex + 1] : null)

    setDeletingLocation(true)
    try {
      await timelineApi.deletePoint(point.id)
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
      await load()
      showRouteNotice()
      toast.success('Location removed')
    } finally {
      setDeletingLocation(false)
    }
  }

  const handleMapEditPoint = (point) => {
    navigate(
      `/trips/${tripId}/points/${point.id}/edit?returnTo=map&focusLat=${point.latitude}&focusLon=${point.longitude}&focusZoom=13`
    )
  }

  const handleMovePoint = async (pointId, direction) => {
    const currentIndex = points.findIndex((point) => point.id === pointId)
    const swapIndex = currentIndex + direction
    if (currentIndex < 0 || swapIndex < 0 || swapIndex >= points.length) return

    const nextPoints = [...points]
    ;[nextPoints[currentIndex], nextPoints[swapIndex]] = [nextPoints[swapIndex], nextPoints[currentIndex]]

    setReorderingLocations(true)
    try {
      await timelineApi.reorderPoints(tripId, nextPoints.map((point) => point.id))
      await load()
      showRouteNotice()
      toast.success('Timeline order updated')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to reorder locations', { duration: 7000 })
    } finally {
      setReorderingLocations(false)
    }
  }

  const handleRegenerateShare = async () => {
    try {
      const updatedTrip = await tripsApi.regenerateShare(tripId)
      setTrip((current) => ({ ...current, ...updatedTrip }))
      toast.success('Share link regenerated')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not regenerate share link')
    }
  }

  if (loading) return <Layout><div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div></Layout>
  if (!trip) return null

  const shareUrl = buildShareUrlFromSlug(trip.share_slug, trip.share_url)
  const isSharedTrip = trip.visibility === 'public' || trip.visibility === 'unlisted'
  const visibilityLabel = trip.visibility === 'public' ? 'Public' : trip.visibility === 'unlisted' ? 'Unlisted' : 'Private'

  return (
    <Layout>
      <div className="space-y-5">
        {deletingLocation && (
          <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-slate-950/35 backdrop-blur-[1px]">
            <div className="flex items-center gap-3 rounded-2xl bg-white px-5 py-4 shadow-xl">
              <LoadingSpinner size="md" />
              <div>
                <p className="text-sm font-semibold text-slate-800">Deleting location...</p>
                <p className="text-xs text-slate-500">Updating map and timeline</p>
              </div>
            </div>
          </div>
        )}
        {reorderingLocations && (
          <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-slate-950/35 backdrop-blur-[1px]">
            <div className="flex items-center gap-3 rounded-2xl bg-white px-5 py-4 shadow-xl">
              <LoadingSpinner size="md" />
              <div>
                <p className="text-sm font-semibold text-slate-800">Updating timeline...</p>
                <p className="text-xs text-slate-500">Saving the new trip order</p>
              </div>
            </div>
          </div>
        )}

        <div>
          <Link to="/trips" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-primary-600 mb-3">
            <ArrowLeft className="w-4 h-4" /> My Trips
          </Link>

          <div
            className="relative min-h-[19rem] overflow-hidden rounded-2xl bg-gradient-to-br from-primary-600 to-sky-500 sm:min-h-[21rem] lg:h-48 lg:min-h-0"
            style={trip.cover_image_url ? { backgroundImage: `url(${trip.cover_image_url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : {}}
          >
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
            <div className="absolute bottom-4 left-4 right-4 sm:left-5 sm:right-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                <div className="min-w-0">
                  <h1 className="max-w-full break-words text-3xl font-bold leading-tight text-white sm:text-2xl">{trip.title}</h1>
                  {(trip.start_date || trip.end_date) && (
                    <p className="mt-2 max-w-full break-words text-sm text-white/70">{fmtDateRange(trip.start_date, trip.end_date)}</p>
                  )}
                  <p className="mt-1 text-xs text-white/70">{visibilityLabel} trip</p>
                  {trip.stats && (
                    <p className="mt-1 max-w-full break-words text-xs text-white/60">
                      {trip.stats.total_points} places | {trip.stats.total_countries} {trip.stats.total_countries === 1 ? 'country' : 'countries'}
                    </p>
                  )}
                </div>
                <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:flex-nowrap sm:justify-end">
                  {isSharedTrip && shareUrl ? (
                    <button
                      onClick={() => { navigator.clipboard.writeText(shareUrl); toast.success('Link copied!') }}
                      className="inline-flex min-h-10 flex-1 items-center justify-center gap-1 rounded-lg bg-white/20 px-3 py-2 text-xs text-white hover:bg-white/30 sm:min-h-0 sm:flex-none sm:py-1.5"
                    >
                      <Share2 className="w-3 h-3" /> Share
                    </button>
                  ) : null}
                  <Link to={`/trips/${tripId}/edit`} className="inline-flex min-h-10 flex-1 items-center justify-center gap-1 rounded-lg bg-white/20 px-3 py-2 text-xs text-white hover:bg-white/30 sm:min-h-0 sm:flex-none sm:py-1.5">
                    <Edit2 className="w-3 h-3" /> Edit
                  </Link>
                  <button onClick={handleDeleteTrip} className="inline-flex min-h-10 flex-1 items-center justify-center gap-1 rounded-lg bg-red-500/80 px-3 py-2 text-xs text-white hover:bg-red-600 sm:min-h-0 sm:flex-none sm:py-1.5">
                    <Trash2 className="w-3 h-3" /> Delete
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-sm font-semibold text-slate-800">Sharing</p>
              <p className="text-xs text-slate-500 mt-1">
                {trip.visibility === 'private'
                  ? 'This trip is private. Switch to Unlisted or Public in Edit Trip to generate a share link.'
                  : trip.visibility === 'unlisted'
                    ? 'Anyone with this link can view the trip, but it will not appear in Shared Trips.'
                    : 'This trip is publicly discoverable and can appear in Shared Trips.'}
              </p>
            </div>
            {isSharedTrip && shareUrl ? (
              <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
                <button
                  type="button"
                  onClick={() => { navigator.clipboard.writeText(shareUrl); toast.success('Link copied!') }}
                  className="min-h-11 rounded-lg bg-primary-600 px-3 py-2 text-xs font-medium text-white hover:bg-primary-700 sm:min-h-0"
                >
                  Copy link
                </button>
                <a
                  href={shareUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50 sm:min-h-0"
                >
                  Open shared page
                </a>
                <button
                  type="button"
                  onClick={handleRegenerateShare}
                  className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50 sm:min-h-0"
                >
                  Regenerate link
                </button>
              </div>
            ) : null}
          </div>
          {isSharedTrip && shareUrl ? (
            <div className="mt-4 space-y-3">
              <div className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600 break-all">{shareUrl}</div>
              <div className="flex flex-wrap gap-4 text-xs text-slate-500">
                <span>{trip.public_stats?.unique_views_total || 0} unique views total</span>
                <span>{trip.public_stats?.unique_views_7d || 0} in last 7 days</span>
                <span>{trip.public_stats?.unique_views_30d || 0} in last 30 days</span>
              </div>
            </div>
          ) : null}
        </div>

        <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-sm font-semibold text-slate-800">Travel Journal</p>
              <p className="text-xs text-slate-500 mt-1">
                Turn this finished route into a readable journal built from your places, notes, companions, and uploaded photos.
              </p>
              {trip.travel_companions ? (
                <p className="mt-2 text-xs text-slate-500">Companions: {trip.travel_companions}</p>
              ) : null}
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              <Link
                to={`/trips/${tripId}/journal`}
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 sm:min-h-0"
              >
                <BookOpen className="h-4 w-4" />
                {trip.journal_exists ? 'Open journal' : 'Create journal'}
              </Link>
              {trip.visibility !== 'private' && trip.share_slug && trip.journal_exists ? (
                <Link
                  to={`/shared/${trip.share_slug}/journal`}
                  className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 sm:min-h-0"
                >
                  Public journal
                </Link>
              ) : null}
            </div>
          </div>
          {!trip.description ? (
            <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              This trip does not have much written description yet, so the journal will lean more on timeline order, route flow, images, and trip metadata.
            </p>
          ) : null}
        </div>

        <div className="flex items-center gap-1 bg-white rounded-xl border border-slate-100 shadow-sm p-1">
          {TABS.map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => updateViewParams(id)}
              className={`flex-1 flex items-center justify-center gap-2 py-2 text-sm font-medium rounded-lg transition-colors ${
                tab === id ? 'bg-primary-600 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-50'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </div>

        <div className="flex justify-stretch sm:justify-end">
          <Link
            to={`/trips/${tripId}/points/new?returnTo=${tab}`}
            className="flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700 sm:min-h-0 sm:w-auto"
          >
            <Plus className="w-4 h-4" /> Add Location
          </Link>
        </div>

        {routeNoticeVisible && (
          <div className="flex items-start justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <div>
              <p className="font-semibold">Timeline updated</p>
              <p className="mt-1 text-amber-800">
                Map marker order already follows the new trip sequence. Some route paths or segment details may need review if you changed the trip order in the middle.
              </p>
            </div>
            <button
              type="button"
              onClick={dismissRouteNotice}
              className="rounded-lg px-2 py-1 text-xs font-medium text-amber-800 hover:bg-amber-100"
            >
              Dismiss
            </button>
          </div>
        )}

        {tab === 'map' && (
          <div className="h-[54vh] min-h-[360px] rounded-xl overflow-hidden border border-slate-100 shadow-sm lg:h-[60vh] 2xl:h-[calc(100vh-21rem)]">
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
          <div className="2xl:max-h-[calc(100vh-21rem)] 2xl:overflow-y-auto 2xl:pr-1">
            <TimelineView
              points={points}
              segments={segments}
              tripId={tripId}
              onDelete={handleDeletePoint}
              onMoveUp={(pointId) => handleMovePoint(pointId, -1)}
              onMoveDown={(pointId) => handleMovePoint(pointId, 1)}
            />
          </div>
        )}

        {tab === 'gallery' && (
          <div className="2xl:max-h-[calc(100vh-21rem)] 2xl:overflow-y-auto 2xl:pr-1">
            <GalleryView points={points} />
          </div>
        )}

        {tab === 'routes' && (
          <div className="divide-y divide-slate-50 rounded-xl border border-slate-100 bg-white shadow-sm 2xl:max-h-[calc(100vh-21rem)] 2xl:overflow-y-auto">
            {segments.length === 0 ? (
              <div className="py-12 text-center text-slate-400">No routes recorded yet.</div>
            ) : (
              segments.map((seg) => {
                const from = points.find((p) => p.id === seg.from_point_id)
                const to = points.find((p) => p.id === seg.to_point_id)
                const method = getMethod(seg.travel_method)
                const Icon = method.Icon
                return (
                  <div key={seg.id} className="flex items-center gap-4 px-5 py-4">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: `${method.color}1a` }}>
                      <Icon className="w-4 h-4" style={{ color: method.color }} />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-slate-700">
                        {from?.place_name || '?'} {'->'} {to?.place_name || '?'}
                      </p>
                      <p className="text-xs text-slate-400">{method.label}{seg.description ? ` | ${seg.description}` : ''}</p>
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
