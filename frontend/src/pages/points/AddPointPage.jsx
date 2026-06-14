import { useState, useCallback, useEffect, useRef } from 'react'
import { useParams, useNavigate, Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Upload, MapPin } from 'lucide-react'
import { useDropzone } from 'react-dropzone'
import { timelineApi } from '../../api/timeline'
import { uploadApi } from '../../api/upload'
import { tripsApi } from '../../api/trips'
import { routesApi } from '../../api/routes'
import Layout from '../../components/layout/Layout'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'
import MapPicker from '../../components/map/MapPicker'
import PlaceSearch from '../../components/ui/PlaceSearch'
import RouteCheckConfirmModal from '../../components/ui/RouteCheckConfirmModal'
import SearchableLocationInput from '../../components/ui/SearchableLocationInput'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import { searchCities, searchCountries } from '../../components/ui/locationSearch'
import { checkTransportRouteBeforeSave } from '../../utils/transportRouteCheck'
import { getVisibleMethods } from '../../utils/travelIcons'
import { getVisitDateRangeError } from '../../utils/visitDate'
import toast from 'react-hot-toast'

const SNAP_METHOD_LABELS = {
  train: 'train station',
  flight: 'airport',
  ferry: 'ferry terminal',
  excursion: 'lift station',
}

function SubmitOverlay({ visible, label, detail }) {
  if (!visible) return null

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-900/45 px-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 text-center shadow-2xl">
        <div className="mx-auto mb-4 flex justify-center">
          <LoadingSpinner size="lg" />
        </div>
        <h2 className="text-lg font-semibold text-slate-800">{label}</h2>
        <p className="mt-2 text-sm text-slate-500">
          {detail}
        </p>
      </div>
    </div>
  )
}

export default function AddPointPage() {
  const { tripId } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [trip, setTrip] = useState(null)
  const [form, setForm] = useState({
    country: '', city: '', place_name: '', description: '',
    visit_date: '', latitude: '', longitude: '',
    image_url: '', travel_method: 'car',
  })
  const [loading, setLoading] = useState(false)
  const [loadingLabel, setLoadingLabel] = useState('Adding location...')
  const [loadingDetail, setLoadingDetail] = useState('Please wait while the location is being added. Do not cancel, refresh, or close this tab.')
  const [uploading, setUploading] = useState(false)
  const [snappingTrainStation, setSnappingTrainStation] = useState(false)
  const [preview, setPreview] = useState(null)
  const [mapFocusTarget, setMapFocusTarget] = useState(null)
  const [trainStation, setTrainStation] = useState(null)
  const [latestPointFocus, setLatestPointFocus] = useState(null)
  const [latestPointCountry, setLatestPointCountry] = useState('')
  const [previousPoint, setPreviousPoint] = useState(null)
  const [insertContext, setInsertContext] = useState(null)
  const [visitedCountries, setVisitedCountries] = useState([])
  const [routeConfirm, setRouteConfirm] = useState({ open: false, message: '', canConfirm: true, title: 'No Route Found' })

  const uploadedUrlRef = useRef(null)
  const submittedRef = useRef(false)
  const previousTravelMethodRef = useRef('')
  const routeConfirmResolverRef = useRef(null)
  const insertAfterPointId = Number(searchParams.get('insertAfter') || 0) || null

  const searchCountriesWithinTrip = useCallback(async (text) => {
    const query = text.trim().toLowerCase()
    const countries = visitedCountries.length > 0
      ? visitedCountries
      : (Array.isArray(trip?.planned_countries) ? trip.planned_countries : [])
    if (countries.length > 0) {
      return countries
        .filter((country) => country.toLowerCase().includes(query))
        .map((country) => ({
          id: `trip-country-${country}`,
          label: country,
          country,
          subtitle: 'Added to this trip',
        }))
    }
    return searchCountries(text)
  }, [trip, visitedCountries])

  const clearDraftForMethodChange = useCallback(() => {
    if (uploadedUrlRef.current && localStorage.getItem('token')) {
      uploadApi.deleteImage(uploadedUrlRef.current).catch(() => {})
      uploadedUrlRef.current = null
    }

    setForm((current) => ({
      ...current,
      // Keep country so the user does not have to re-select it after switching methods.
      city: '',
      place_name: '',
      description: '',
      visit_date: '',
      latitude: '',
      longitude: '',
      image_url: '',
    }))
    setPreview(null)
    setMapFocusTarget(null)
    setTrainStation(null)
    setSnappingTrainStation(false)
  }, [])

  useEffect(() => {
    return () => {
      if (!submittedRef.current && uploadedUrlRef.current && localStorage.getItem('token')) {
        uploadApi.deleteImage(uploadedUrlRef.current).catch(() => {})
      }
    }
  }, [])

  useEffect(() => {
    Promise.all([
      tripsApi.get(tripId),
      timelineApi.listPoints(tripId),
    ]).then(([tripData, points]) => {
      setTrip(tripData)
      const sortedPoints = [...points].sort((a, b) => b.sequence_no - a.sequence_no)
      const orderedPoints = [...points].sort((a, b) => a.sequence_no - b.sequence_no)
      const latestPoint = sortedPoints.find((point) => point.latitude && point.longitude)
      const uniqueCountries = [...new Set(
        sortedPoints.map((p) => p.country).filter(Boolean)
      )].sort()
      setVisitedCountries(uniqueCountries)
      if (insertAfterPointId) {
        const insertIndex = orderedPoints.findIndex((point) => point.id === insertAfterPointId)
        const afterPoint = insertIndex >= 0 ? orderedPoints[insertIndex] : null
        const beforePoint = insertIndex >= 0 && insertIndex < orderedPoints.length - 1
          ? orderedPoints[insertIndex + 1]
          : null
        setPreviousPoint(afterPoint || null)
        setInsertContext(afterPoint ? {
          afterPointId: afterPoint.id,
          afterPointName: afterPoint.place_name,
          beforePointName: beforePoint?.place_name || null,
          minDate: afterPoint.visit_date || tripData?.start_date || '',
          maxDate: beforePoint?.visit_date || tripData?.end_date || '',
        } : null)
        if (afterPoint?.latitude && afterPoint?.longitude) {
          setLatestPointFocus({
            lat: Number(afterPoint.latitude),
            lng: Number(afterPoint.longitude),
            zoom: 9,
          })
        }
        setLatestPointCountry(afterPoint?.country || '')
        setForm((current) => current.visit_date ? current : ({
          ...current,
          visit_date: beforePoint?.visit_date || afterPoint?.visit_date || tripData?.start_date || '',
        }))
      } else if (latestPoint) {
        setPreviousPoint(latestPoint || null)
        setInsertContext(null)
        setLatestPointFocus({
          lat: Number(latestPoint.latitude),
          lng: Number(latestPoint.longitude),
          zoom: 9,
        })
        setLatestPointCountry(latestPoint.country || '')
        setForm((current) => current.visit_date ? current : ({
          ...current,
          visit_date: latestPoint.visit_date || tripData?.start_date || '',
        }))
      } else if (tripData?.starting_latitude != null && tripData?.starting_longitude != null) {
        setPreviousPoint(null)
        setInsertContext(null)
        setLatestPointFocus({
          lat: Number(tripData.starting_latitude),
          lng: Number(tripData.starting_longitude),
          zoom: 7,
        })
        setLatestPointCountry(tripData.starting_country || '')
        setForm((current) => current.visit_date ? current : ({
          ...current,
          visit_date: tripData?.start_date || '',
        }))
      } else if (tripData?.start_date) {
        setPreviousPoint(null)
        setInsertContext(null)
        setForm((current) => current.visit_date ? current : ({
          ...current,
          visit_date: tripData.start_date,
        }))
      }
    }).catch(() => {})
  }, [tripId])

  useEffect(() => {
    if (!latestPointCountry) return
    setForm((current) => current.country ? current : ({ ...current, country: latestPointCountry }))
  }, [latestPointCountry])

  useEffect(() => {
    if (!mapFocusTarget && !form.latitude && !form.longitude && latestPointFocus) {
      setMapFocusTarget(latestPointFocus)
    }
  }, [latestPointFocus, mapFocusTarget, form.latitude, form.longitude])

  useEffect(() => {
    if (!loading) return undefined

    const handleBeforeUnload = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [loading])

  const requestRouteConfirmation = useCallback((message) => {
    return new Promise((resolve) => {
      routeConfirmResolverRef.current = resolve
      setRouteConfirm({ open: true, message, canConfirm: true, title: 'No Route Found' })
    })
  }, [])

  const closeRouteConfirmation = useCallback((accepted) => {
    setRouteConfirm({ open: false, message: '', canConfirm: true, title: 'No Route Found' })
    if (routeConfirmResolverRef.current) {
      routeConfirmResolverRef.current(accepted)
      routeConfirmResolverRef.current = null
    }
  }, [])

  const showBlockedRouteDialog = useCallback((message) => {
    setRouteConfirm({
      open: true,
      message,
      canConfirm: false,
      title: 'Cannot Add Route',
    })
  }, [])

  const set = (key) => (e) => setForm((current) => ({ ...current, [key]: e.target.value }))

  const isSnapMethod = Boolean(SNAP_METHOD_LABELS[form.travel_method])

  const applyLocationResult = useCallback((location, zoom = 13) => {
    setForm((current) => ({
      ...current,
      place_name: location.place_name || current.place_name,
      city: location.city || current.city,
      country: location.country || current.country,
      latitude: location.latitude,
      longitude: location.longitude,
    }))
    setMapFocusTarget({
      lat: Number(location.latitude),
      lng: Number(location.longitude),
      zoom,
    })
  }, [])

  const snapToNearestTransportPlace = useCallback(async (lat, lon, method, options = {}) => {
    const { showSuccess = true, countryHint } = options
    setSnappingTrainStation(true)
    setTrainStation(null)
    // Clear location fields but preserve country so it survives if snap fails.
    setForm((current) => ({
      ...current,
      place_name: '',
      city: '',
      latitude: '',
      longitude: '',
    }))
    setMapFocusTarget(null)

    try {
      const result = method === 'train'
        ? await routesApi.nearestTrainStation({ lat, lon, country: countryHint })
        : await routesApi.nearestTransportPlace({ lat, lon, method, country: countryHint })
      const station = method === 'train' ? result.station : result.place
      if (!station) {
        if (countryHint) {
          // Reverse-geocode the clicked point so we can tell the user which
          // country they actually clicked in rather than just saying "not found".
          try {
            const rev = await routesApi.reverseLocation({ lat, lon })
            const actualCountry = rev?.location?.country
            if (actualCountry && actualCountry.toLowerCase() !== countryHint.toLowerCase()) {
              toast.error(`This location is in ${actualCountry}. Please click within ${countryHint}.`)
            } else {
              toast.error(`No ${SNAP_METHOD_LABELS[method]} found in ${countryHint}. Click closer to one.`)
            }
          } catch {
            toast.error(`No ${SNAP_METHOD_LABELS[method]} found in ${countryHint}. Click within the selected country.`)
          }
        } else {
          toast.error(`No ${SNAP_METHOD_LABELS[method]} found nearby. Choose closer to one.`)
        }
        return false
      }

      const normalizedStation = {
        place_name: station.place_name || station.name,
        city: station.city || '',
        // Prefer the countryHint (exact dropdown value) when the snap result's
        // country matches it case-insensitively — the snap result may return a
        // lowercased inferred name that won't match a <select> option.
        country: (countryHint && station.country && station.country.toLowerCase() === countryHint.toLowerCase())
          ? countryHint
          : (station.country || countryHint || ''),
        latitude: station.latitude,
        longitude: station.longitude,
      }
      setTrainStation(normalizedStation)
      applyLocationResult(normalizedStation)

      if (showSuccess) {
        toast.success(`Snapped to ${normalizedStation.place_name}`)
      }

      return true
    } catch {
      toast.error(`Failed to find a nearby ${SNAP_METHOD_LABELS[method]}`)
      return false
    } finally {
      setSnappingTrainStation(false)
    }
  }, [applyLocationResult])

  const reverseGeocodeMapPick = useCallback(async (lat, lon, expectedCountry = null) => {
    setSnappingTrainStation(true)
    setTrainStation(null)

    try {
      const { location } = await routesApi.reverseLocation({ lat, lon })
      if (!location) {
        toast.error('Failed to identify this location')
        return false
      }

      // Reject the pick if a country is selected and the clicked point is outside it.
      if (expectedCountry && location.country) {
        const norm = (s) => s.trim().toLowerCase()
        if (norm(location.country) !== norm(expectedCountry)) {
          toast.error(`This location is in ${location.country}. Please click within ${expectedCountry}.`)
          return false
        }
      }

      applyLocationResult({
        place_name: location.place_name,
        city: location.city,
        country: location.country,
        latitude: location.latitude,
        longitude: location.longitude,
      })
      toast.success('Location details filled from the map')
      return true
    } catch {
      toast.error('Failed to identify this location')
      return false
    } finally {
      setSnappingTrainStation(false)
    }
  }, [applyLocationResult])

  useEffect(() => {
    const previousMethod = previousTravelMethodRef.current
    const currentMethod = form.travel_method

    if (!previousMethod || previousMethod === currentMethod) {
      previousTravelMethodRef.current = currentMethod
      return
    }

    clearDraftForMethodChange()
    previousTravelMethodRef.current = currentMethod
  }, [
    clearDraftForMethodChange,
    form.travel_method,
  ])

  const handlePlaceSelect = ({ place_name, city, country, latitude, longitude }) => {
    applyLocationResult({
      place_name: place_name || '',
      city: city || '',
      country: country || '',
      latitude,
      longitude,
    }, city ? 11 : 6)
    if (isSnapMethod) {
      setTrainStation({
        place_name: place_name || '',
        latitude: Number(latitude),
        longitude: Number(longitude),
        city: city || '',
        country: country || '',
      })
    }
    toast.success('Location auto-filled!')
  }

  const onDrop = useCallback(async (files) => {
    const file = files[0]
    if (!file) return
    setPreview(URL.createObjectURL(file))
    setUploading(true)
    try {
      const res = await uploadApi.image(file)
      uploadedUrlRef.current = res.url
      setForm((current) => ({
        ...current,
        image_url: res.url,
        latitude: res.exif?.latitude ?? current.latitude,
        longitude: res.exif?.longitude ?? current.longitude,
        visit_date: res.exif?.date_taken
          ? res.exif.date_taken.slice(0, 10).replace(/:/g, '-')
          : current.visit_date,
      }))
      if (res.exif) toast.success('GPS and date auto-filled from photo!')
      else toast.success('Photo uploaded')
    } catch (err) {
      toast.error(err.message || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/*': [] },
    maxFiles: 1,
  })

  const handleMapPick = (lat, lon) => {
    if (isSnapMethod) {
      snapToNearestTransportPlace(lat, lon, form.travel_method, { countryHint: form.country })
      return
    }

    reverseGeocodeMapPick(lat, lon, form.country || null)
  }

  const minVisitDate = insertContext?.minDate || previousPoint?.visit_date || trip?.start_date || ''
  const maxVisitDate = insertContext?.maxDate || trip?.end_date || ''
  const dateError = getVisitDateRangeError(form.visit_date, trip, {
    minDate: minVisitDate || undefined,
    maxDate: maxVisitDate || undefined,
  })

  const buildReturnUrl = (focusTarget = null, options = {}) => {
    const { includeRouteNotice = false } = options
    const returnTo = searchParams.get('returnTo') || 'timeline'
    const params = new URLSearchParams({ tab: returnTo })
    if (includeRouteNotice) {
      params.set('routeNotice', '1')
    }
    if (
      returnTo === 'map'
      && focusTarget
      && Number.isFinite(focusTarget.lat)
      && Number.isFinite(focusTarget.lng)
    ) {
      params.set('focusLat', String(focusTarget.lat))
      params.set('focusLon', String(focusTarget.lng))
      params.set('focusZoom', String(focusTarget.zoom ?? 12))
    }
    return `/trips/${tripId}?${params.toString()}`
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (loading) {
      return
    }
    if (isSnapMethod && !trainStation) {
      toast.error(`Choose a ${SNAP_METHOD_LABELS[form.travel_method]} from search or by clicking near one on the map`)
      return
    }
    if (dateError) {
      toast.error(dateError)
      return
    }

    setLoading(true)
    setLoadingLabel('Checking route...')
    setLoadingDetail('Please wait while we validate the route before adding this location. Do not cancel, refresh, or close this tab.')

    if (previousPoint && form.travel_method) {
      const routeCheck = await checkTransportRouteBeforeSave({
        method: form.travel_method,
        fromPoint: previousPoint,
        toPoint: {
          latitude: form.latitude,
          longitude: form.longitude,
          country: form.country,
        },
      })
      if (routeCheck.behavior === 'block') {
        setLoading(false)
        showBlockedRouteDialog(routeCheck.message || 'No route found')
        return
      }
      if (routeCheck.behavior === 'confirm') {
        setLoading(false)
        const accepted = await requestRouteConfirmation(routeCheck.message || 'No route found. Continue anyway?')
        if (!accepted) {
          return
        }
        setLoading(true)
        setLoadingLabel('Adding location...')
        setLoadingDetail('Please wait while the location is being added. Do not cancel, refresh, or close this tab.')
      }
    }

    setLoadingLabel('Adding location...')
    setLoadingDetail('Please wait while the location is being added. Do not cancel, refresh, or close this tab.')
    try {
      const payload = {
        country: form.country,
        city: form.city || null,
        place_name: form.place_name,
        description: form.description || null,
        visit_date: form.visit_date,
        latitude: form.latitude !== '' ? parseFloat(form.latitude) : null,
        longitude: form.longitude !== '' ? parseFloat(form.longitude) : null,
        image_url: form.image_url || null,
        insert_after_point_id: insertContext?.afterPointId || null,
        travel_method: form.travel_method || null,
      }
      await timelineApi.addPoint(tripId, payload)
      submittedRef.current = true
      toast.success('Location added!')
      navigate(buildReturnUrl({
        lat: payload.latitude ?? Number(form.latitude),
        lng: payload.longitude ?? Number(form.longitude),
        zoom: 13,
      }, { includeRouteNotice: true }))
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to add location')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Layout>
      <SubmitOverlay visible={loading} label={loadingLabel} detail={loadingDetail} />
      <RouteCheckConfirmModal
        open={routeConfirm.open}
        title={routeConfirm.title}
        message={routeConfirm.message}
        canConfirm={routeConfirm.canConfirm}
        onConfirm={() => closeRouteConfirmation(true)}
        onCancel={() => closeRouteConfirmation(false)}
        cancelLabel={routeConfirm.canConfirm ? 'Cancel' : 'Okay'}
      />
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <Link to={buildReturnUrl()} className="p-2 hover:bg-slate-100 rounded-lg">
            <ArrowLeft className="w-5 h-5 text-slate-500" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-slate-800">
              {insertContext ? 'Add Location Between Stops' : 'Add Location'}
            </h1>
            {trip && (trip.start_date || trip.end_date) && (
              <p className="text-xs text-slate-400 mt-0.5">
                Trip date range: {trip.start_date || '-'} to {trip.end_date || '-'}
              </p>
            )}
            {insertContext ? (
              <p className="text-xs text-primary-600 mt-1">
                This stop will be inserted after {insertContext.afterPointName}
                {insertContext.beforePointName ? ` and before ${insertContext.beforePointName}` : ''}.
              </p>
            ) : null}
          </div>
        </div>

        <form onSubmit={handleSubmit} className={`space-y-5 ${loading ? 'pointer-events-none opacity-80' : ''}`}>
          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-3">
            <h2 className="font-semibold text-slate-700">How did you get here?</h2>
            <div className="grid grid-cols-3 sm:grid-cols-7 gap-2">
              {getVisibleMethods(trip?.category).map(({ value, label, Icon, color }) => (
                <button
                  key={value}
                  type="button"
                  disabled={loading}
                  onClick={() => setForm((current) => ({ ...current, travel_method: current.travel_method === value ? '' : value }))}
                  className={`flex flex-col items-center gap-1 p-3 rounded-xl border-2 text-xs font-medium transition-all
                    ${form.travel_method === value
                      ? 'border-transparent text-white'
                      : 'border-slate-100 text-slate-500 hover:border-slate-200'}`}
                  style={form.travel_method === value ? { background: color, borderColor: color } : {}}
                >
                  <Icon className="w-5 h-5" />
                  {label}
                </button>
              ))}
            </div>
            {form.travel_method === 'excursion' && trip?.category === 'Europe Trip' && (
              <p className="text-xs text-amber-600">
                Excursion lift support is available for Europe only for now. Cable car, gondola, and similar lift stations will use the Europe lift dataset when available.
              </p>
            )}
          </div>

          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-3">
            <h2 className="font-semibold text-slate-700 flex items-center gap-2">
              <Upload className="w-4 h-4 text-primary-500" /> Photo
              <span className="text-xs text-slate-400 font-normal">(GPS and date auto-detected from EXIF)</span>
            </h2>
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors
                ${isDragActive ? 'border-primary-400 bg-primary-50' : 'border-slate-200 hover:border-primary-300'}`}
            >
              <input {...getInputProps()} />
              {preview ? (
                <img src={preview} alt="preview" className="max-h-48 mx-auto rounded-lg object-cover" />
              ) : (
                <div className="space-y-2 text-slate-400">
                  <Upload className="w-8 h-8 mx-auto" />
                  <p className="text-sm">{isDragActive ? 'Drop here' : 'Drag and drop or click to upload'}</p>
                  <p className="text-xs">JPEG, PNG, WebP, HEIC - max 20 MB</p>
                </div>
              )}
              {uploading && (
                <p className="mt-2 inline-flex items-center gap-2 text-sm text-primary-500">
                  <LoadingSpinner size="sm" />
                  Uploading...
                </p>
              )}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-4">
            <h2 className="font-semibold text-slate-700">Place details</h2>

            <PlaceSearch
              label="Search place (auto-fill all fields)"
              onSelect={handlePlaceSelect}
              travelMethod={form.travel_method || ''}
              country={(form.country || latestPointCountry || '').trim()}
              multiCountry={(trip?.planned_countries?.length ?? 0) > 1}
            />

            <div className="border-t border-slate-50 pt-4 grid grid-cols-2 gap-4">
              {Array.isArray(trip?.planned_countries) && trip.planned_countries.length > 0 ? (
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Country *
                  </label>
                  <select
                    value={form.country}
                    onChange={(e) => {
                      const newCountry = e.target.value
                      setForm((current) => ({
                        ...current,
                        country: newCountry,
                        place_name: '',
                        city: '',
                        latitude: '',
                        longitude: '',
                      }))
                      setTrainStation(null)
                      setMapFocusTarget(null)
                    }}
                    required
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">Select country</option>
                    {trip.planned_countries.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
              ) : (
                <SearchableLocationInput
                  label="Country *"
                  value={form.country}
                  onChange={(value) => setForm((current) => ({ ...current, country: value }))}
                  onSelect={(result) => {
                    setForm((current) => ({
                      ...current,
                      country: result.country || result.label,
                      city: current.city,
                      place_name: '',
                      latitude: '',
                      longitude: '',
                    }))
                    setTrainStation(null)
                    setMapFocusTarget(null)
                    if (result.latitude && result.longitude) {
                      setMapFocusTarget({
                        lat: Number(result.latitude),
                        lng: Number(result.longitude),
                        zoom: 5,
                      })
                    }
                  }}
                  searchFn={searchCountriesWithinTrip}
                  required
                  placeholder="Search country"
                />
              )}
              <SearchableLocationInput
                label="City"
                value={form.city}
                onChange={(value) => setForm((current) => ({ ...current, city: value }))}
                onSelect={(result) => {
                  setForm((current) => ({
                    ...current,
                    city: result.city || result.label,
                    country: result.country || current.country,
                  }))
                  if (isSnapMethod) {
                    setTrainStation(null)
                  }
                  if (result.latitude && result.longitude) {
                    setMapFocusTarget({
                      lat: Number(result.latitude),
                      lng: Number(result.longitude),
                      zoom: 10,
                    })
                  }
                }}
                searchFn={(text) => searchCities(text, form.country)}
                placeholder={form.country ? `Search city in ${form.country}` : 'Search city'}
                disabled={isSnapMethod}
              />
            </div>
            {isSnapMethod && (
              <p className="text-xs text-slate-400 -mt-1">
                {form.travel_method === 'train'
                  ? 'Train locations must be selected from train station search or snapped from the map. Changing country resets the selection.'
                  : `This ${form.travel_method} stop should be selected from search or snapped to the nearest ${SNAP_METHOD_LABELS[form.travel_method]}. Changing country resets the selection.`}
              </p>
            )}
            <Input
              label="Place name *"
              value={form.place_name}
              onChange={set('place_name')}
              required
              placeholder="Lauterbrunnen Valley"
              readOnly={isSnapMethod}
              className={isSnapMethod ? 'bg-slate-50' : ''}
            />

            <Input
              label="Visit date *"
              type="date"
              value={form.visit_date}
              onChange={set('visit_date')}
              required
              min={minVisitDate || undefined}
              max={maxVisitDate || undefined}
            />

            {dateError ? (
              <p className="text-xs text-red-500 -mt-2">{dateError}</p>
            ) : (
              minVisitDate && maxVisitDate && (
                <p className="text-xs text-slate-400 -mt-2">
                  {insertContext
                    ? `This timeline slot accepts dates from ${minVisitDate} to ${maxVisitDate}.`
                    : `New locations can use dates from ${minVisitDate} to ${maxVisitDate}. Earlier dates belong to already-added locations.`}
                </p>
              )
            )}
            <p className="text-xs text-amber-600 -mt-1">
              Choose the visit date carefully. The timeline follows date order, so using the wrong date can change or reverse the trip sequence.
            </p>

            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-slate-700">Description</label>
              <textarea
                value={form.description}
                onChange={set('description')}
                rows={3}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
                placeholder="What did you do here?"
              />
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-4">
            <h2 className="font-semibold text-slate-700 flex items-center gap-2">
              <MapPin className="w-4 h-4 text-primary-500" /> Location
              <span className="text-xs text-slate-400 font-normal">(auto-filled from search or photo)</span>
            </h2>
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Latitude"
                type="number"
                step="any"
                value={form.latitude}
                onChange={set('latitude')}
                placeholder="46.5935"
                readOnly={isSnapMethod}
                className={isSnapMethod ? 'bg-slate-50' : ''}
              />
              <Input
                label="Longitude"
                type="number"
                step="any"
                value={form.longitude}
                onChange={set('longitude')}
                placeholder="7.9091"
                readOnly={isSnapMethod}
                className={isSnapMethod ? 'bg-slate-50' : ''}
              />
            </div>
            <MapPicker
              lat={form.latitude}
              lon={form.longitude}
              onChange={handleMapPick}
              focusTarget={mapFocusTarget}
              isLoading={snappingTrainStation}
              loadingText={isSnapMethod
                ? `Finding the nearest ${SNAP_METHOD_LABELS[form.travel_method]}...`
                : 'Identifying this location...'}
              helperText={isSnapMethod
                ? (snappingTrainStation
                  ? `Finding the nearest ${SNAP_METHOD_LABELS[form.travel_method]}...`
                  : `Click on the map and wait until it snaps to a ${SNAP_METHOD_LABELS[form.travel_method]}`)
                : 'Click on the map to place a pin and auto-fill the location'}
            />
          </div>

          <div className="flex gap-3">
            <Button
              type="submit"
              loading={loading}
              disabled={loading || uploading || snappingTrainStation || (isSnapMethod && !trainStation)}
              className="flex-1"
              size="lg"
            >
              {insertContext ? 'Insert location' : 'Add location'}
            </Button>
            <Link
              to={buildReturnUrl()}
              onClick={(event) => {
                if (loading) event.preventDefault()
              }}
              className={loading ? 'pointer-events-none' : ''}
              aria-disabled={loading}
            >
              <Button type="button" variant="secondary" size="lg" disabled={loading}>Cancel</Button>
            </Link>
          </div>
        </form>
      </div>
    </Layout>
  )
}
