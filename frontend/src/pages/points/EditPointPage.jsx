import { useState, useEffect, useCallback, useRef } from 'react'
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
import { searchCities, searchCountries } from '../../components/ui/locationSearch'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
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

export default function EditPointPage() {
  const { tripId, pointId } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [trip, setTrip] = useState(null)
  const [form, setForm] = useState(null)
  const [travelMethod, setTravelMethod] = useState('')
  const [incomingSegment, setIncomingSegment] = useState(null)
  const [outgoingSegment, setOutgoingSegment] = useState(null)
  const [prevPointId, setPrevPointId] = useState(null)
  const [prevPoint, setPrevPoint] = useState(null)
  const [nextPoint, setNextPoint] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savingLabel, setSavingLabel] = useState('Saving location...')
  const [savingDetail, setSavingDetail] = useState('Please wait while the location is being saved. Do not cancel, refresh, or close this tab.')
  const [preview, setPreview] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [snappingTransportPlace, setSnappingTransportPlace] = useState(false)
  const [mapFocusTarget, setMapFocusTarget] = useState(null)
  const [trainStation, setTrainStation] = useState(null)
  const [routeConfirm, setRouteConfirm] = useState({ open: false, message: '', canConfirm: true, title: 'No Route Found' })
  const [visitedCountries, setVisitedCountries] = useState([])

  const originalUrlRef = useRef(null)
  const newlyUploadedRef = useRef(null)
  const submittedRef = useRef(false)
  const previousTravelMethodRef = useRef('')
  const routeConfirmResolverRef = useRef(null)

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

  const clearLocationFields = useCallback(() => {
    setForm((current) => current ? ({
      ...current,
      // Keep country so the user does not need to re-select it after switching methods.
      city: '',
      place_name: '',
      latitude: '',
      longitude: '',
    }) : current)
    setMapFocusTarget(null)
    setTrainStation(null)
  }, [])

  useEffect(() => {
    return () => {
      if (!submittedRef.current && newlyUploadedRef.current && localStorage.getItem('token')) {
        uploadApi.deleteImage(newlyUploadedRef.current).catch(() => {})
      }
    }
  }, [])

  useEffect(() => {
    if (!saving) return undefined

    const handleBeforeUnload = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [saving])

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
      title: 'Cannot Save Route',
    })
  }, [])

  useEffect(() => {
    Promise.all([
      tripsApi.get(tripId),
      timelineApi.listPoints(tripId),
      timelineApi.listSegments(tripId),
    ]).then(([tripData, pts, segs]) => {
      setTrip(tripData)

      const pt = pts.find((point) => point.id === parseInt(pointId, 10))
      if (!pt) {
        navigate(`/trips/${tripId}`)
        return
      }

      setForm({
        country: pt.country,
        city: pt.city || '',
        place_name: pt.place_name,
        description: pt.description || '',
        visit_date: pt.visit_date || '',
        latitude: pt.latitude ?? '',
        longitude: pt.longitude ?? '',
        image_url: pt.image_url || '',
      })

      if (pt.image_url) setPreview(pt.image_url)
      originalUrlRef.current = pt.image_url || null
      if (pt.latitude && pt.longitude) {
        setMapFocusTarget({
          lat: Number(pt.latitude),
          lng: Number(pt.longitude),
          zoom: 13,
        })
      }

      const seg = segs.find((segment) => segment.to_point_id === parseInt(pointId, 10))
      if (seg) {
        setIncomingSegment(seg)
        setTravelMethod(seg.travel_method || '')
        if (SNAP_METHOD_LABELS[seg.travel_method] && pt.latitude && pt.longitude) {
          setTrainStation({
            place_name: pt.place_name,
            latitude: Number(pt.latitude),
            longitude: Number(pt.longitude),
            city: pt.city || '',
            country: pt.country || '',
          })
        }
      }
      setOutgoingSegment(segs.find((segment) => segment.from_point_id === parseInt(pointId, 10)) || null)

      const sorted = [...pts].sort((a, b) => a.sequence_no - b.sequence_no)
      const idx = sorted.findIndex((point) => point.id === parseInt(pointId, 10))
      if (idx > 0) {
        setPrevPointId(sorted[idx - 1].id)
        setPrevPoint(sorted[idx - 1])
      }
      if (idx >= 0 && idx < sorted.length - 1) {
        setNextPoint(sorted[idx + 1])
      }

      const uniqueCountries = [...new Set(
        pts.map((p) => p.country).filter(Boolean)
      )].sort()
      setVisitedCountries(uniqueCountries)
    }).finally(() => setLoading(false))
  }, [tripId, pointId, navigate])

  const set = (key) => (e) => setForm((current) => ({ ...current, [key]: e.target.value }))

  const onDrop = useCallback(async (files) => {
    const file = files[0]
    if (!file) return
    setPreview(URL.createObjectURL(file))
    setUploading(true)
    try {
      const res = await uploadApi.image(file)
      newlyUploadedRef.current = res.url
      setForm((current) => ({
        ...current,
        image_url: res.url,
        latitude: res.exif?.latitude ?? current.latitude,
        longitude: res.exif?.longitude ?? current.longitude,
        visit_date: res.exif?.date_taken
          ? res.exif.date_taken.slice(0, 10).replace(/:/g, '-')
          : current.visit_date,
      }))
      if (res.exif?.latitude && res.exif?.longitude) {
        setMapFocusTarget({
          lat: Number(res.exif.latitude),
          lng: Number(res.exif.longitude),
          zoom: 13,
        })
      }
      if (res.exif) toast.success('GPS and date auto-filled from photo!')
      else toast.success('Photo updated')
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

  const editMinVisitDate = prevPoint?.visit_date || trip?.start_date || ''
  const editMaxVisitDate = nextPoint?.visit_date || trip?.end_date || ''
  const dateError = form ? getVisitDateRangeError(form.visit_date, trip, {
    minDate: editMinVisitDate || undefined,
    maxDate: editMaxVisitDate || undefined,
  }) : ''

  const isSnapMethod = Boolean(SNAP_METHOD_LABELS[travelMethod])

  const applyLocationResult = useCallback((location, zoom = 13) => {
    setForm((current) => current ? ({
      ...current,
      place_name: location.place_name || current.place_name,
      city: location.city || current.city,
      country: location.country || current.country,
      latitude: location.latitude,
      longitude: location.longitude,
    }) : current)
    setMapFocusTarget({
      lat: Number(location.latitude),
      lng: Number(location.longitude),
      zoom,
    })
  }, [])

  const snapToNearestTransportPlace = useCallback(async (lat, lon, method, options = {}) => {
    const { showSuccess = true, countryHint } = options
    setSnappingTransportPlace(true)
    setTrainStation(null)
    setForm((current) => current ? ({
      ...current,
      city: '',
      place_name: '',
      latitude: '',
      longitude: '',
    }) : current)
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
      setSnappingTransportPlace(false)
    }
  }, [applyLocationResult])

  const reverseGeocodeMapPick = useCallback(async (lat, lon, expectedCountry = null) => {
    setSnappingTransportPlace(true)
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
      setSnappingTransportPlace(false)
    }
  }, [applyLocationResult])

  useEffect(() => {
    if (!form) return

    const previousMethod = previousTravelMethodRef.current

    if (!previousMethod || previousMethod === travelMethod) {
      if (!isSnapMethod) {
        setTrainStation(null)
      } else if (form.latitude && form.longitude && !trainStation) {
        setTrainStation({
          place_name: form.place_name,
          latitude: Number(form.latitude),
          longitude: Number(form.longitude),
          city: form.city || '',
          country: form.country || '',
        })
      }
      previousTravelMethodRef.current = travelMethod
      return
    }

    if (!travelMethod) {
      clearLocationFields()
      previousTravelMethodRef.current = travelMethod
      return
    }

    if (isSnapMethod) {
      if (form.latitude !== '' && form.longitude !== '') {
        snapToNearestTransportPlace(Number(form.latitude), Number(form.longitude), travelMethod, { showSuccess: false, countryHint: form.country })
      } else {
        clearLocationFields()
      }
      previousTravelMethodRef.current = travelMethod
      return
    }

    setTrainStation(null)
    previousTravelMethodRef.current = travelMethod
  }, [
    clearLocationFields,
    form,
    form?.city,
    form?.country,
    form?.latitude,
    form?.longitude,
    form?.place_name,
    isSnapMethod,
    snapToNearestTransportPlace,
    trainStation,
    travelMethod,
  ])

  const buildReturnUrl = (focusTarget = null) => {
    const returnTo = searchParams.get('returnTo') || 'timeline'
    const params = new URLSearchParams({ tab: returnTo })
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

  const handleMapPick = (lat, lon) => {
    if (isSnapMethod) {
      snapToNearestTransportPlace(lat, lon, travelMethod, { countryHint: form?.country })
      return
    }

    reverseGeocodeMapPick(lat, lon, form?.country || null)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (saving) {
      return
    }
    if (isSnapMethod && !trainStation) {
      toast.error(`Choose a ${SNAP_METHOD_LABELS[travelMethod]} from search or by clicking near one on the map`)
      return
    }
    if (dateError) {
      toast.error(dateError)
      return
    }

    setSaving(true)
    setSavingLabel('Checking route...')
    setSavingDetail('Please wait while we validate the route before saving this location. Do not cancel, refresh, or close this tab.')

    const pendingPoint = {
      ...form,
      latitude: form.latitude,
      longitude: form.longitude,
      country: form.country,
    }

    const validateRouteChange = async ({ label, method, fromPoint, toPoint }) => {
      if (!method || !fromPoint || !toPoint) {
        return true
      }
      const routeCheck = await checkTransportRouteBeforeSave({
        method,
        fromPoint,
        toPoint,
      })
      if (routeCheck.behavior === 'block') {
        setSaving(false)
        showBlockedRouteDialog(`${label}: ${routeCheck.message || 'No route found'}`)
        return false
      }
      if (routeCheck.behavior !== 'confirm') {
        return true
      }

      setSaving(false)
      const accepted = await requestRouteConfirmation(`${label}: ${routeCheck.message || 'No route found. Continue anyway?'}`)
      if (!accepted) {
        return false
      }
      setSaving(true)
      setSavingLabel('Checking route...')
      setSavingDetail('Please wait while we validate the route before saving this location. Do not cancel, refresh, or close this tab.')
      return true
    }

    if (prevPoint && travelMethod) {
      const isValid = await validateRouteChange({
        label: 'Route into this location',
        method: travelMethod,
        fromPoint: prevPoint,
        toPoint: pendingPoint,
      })
      if (!isValid) {
        return
      }
    }

    if (nextPoint && outgoingSegment?.travel_method) {
      const isValid = await validateRouteChange({
        label: 'Route to the next location',
        method: outgoingSegment.travel_method,
        fromPoint: pendingPoint,
        toPoint: nextPoint,
      })
      if (!isValid) {
        return
      }
    }

    setSavingLabel('Saving location...')
    setSavingDetail('Please wait while the location is being saved. Do not cancel, refresh, or close this tab.')
    try {
      await timelineApi.updatePoint(pointId, {
        ...form,
        latitude: form.latitude !== '' ? parseFloat(form.latitude) : null,
        longitude: form.longitude !== '' ? parseFloat(form.longitude) : null,
        city: form.city || null,
        description: form.description || null,
        image_url: form.image_url || null,
      })

      if (incomingSegment) {
        if (travelMethod && travelMethod !== incomingSegment.travel_method) {
          await timelineApi.updateSegment(incomingSegment.id, { travel_method: travelMethod })
        } else if (!travelMethod) {
          await timelineApi.deleteSegment(incomingSegment.id)
        }
      } else if (travelMethod && prevPointId && !incomingSegment) {
        await timelineApi.createSegment(tripId, {
          from_point_id: prevPointId,
          to_point_id: parseInt(pointId, 10),
          travel_method: travelMethod,
        })
      }

      submittedRef.current = true
      toast.success('Location updated')
      navigate(buildReturnUrl({
        lat: form.latitude !== '' ? parseFloat(form.latitude) : null,
        lng: form.longitude !== '' ? parseFloat(form.longitude) : null,
        zoom: 13,
      }))
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update')
    } finally {
      setSaving(false)
    }
  }

  if (loading || !form) {
    return <Layout><div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div></Layout>
  }

  return (
    <Layout>
      <SubmitOverlay visible={saving} label={savingLabel} detail={savingDetail} />
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
          <Link to={`/trips/${tripId}`} className="p-2 hover:bg-slate-100 rounded-lg">
            <ArrowLeft className="w-5 h-5 text-slate-500" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Edit Location</h1>
            {trip && (trip.start_date || trip.end_date) && (
              <p className="text-xs text-slate-400 mt-0.5">
                Trip date range: {trip.start_date || '-'} to {trip.end_date || '-'}
              </p>
            )}
          </div>
        </div>

        <form onSubmit={handleSubmit} className={`space-y-5 ${saving ? 'pointer-events-none opacity-80' : ''}`}>
          {prevPointId && (
            <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-3">
              <h2 className="font-semibold text-slate-700">How did you get here?</h2>
              <div className="grid grid-cols-3 sm:grid-cols-7 gap-2">
                {getVisibleMethods(trip?.category).map(({ value, label, Icon, color }) => (
                  <button
                    key={value}
                    type="button"
                    disabled={saving}
                    onClick={() => setTravelMethod((current) => current === value ? '' : value)}
                    className={`flex flex-col items-center gap-1 p-3 rounded-xl border-2 text-xs font-medium transition-all
                      ${travelMethod === value
                        ? 'border-transparent text-white'
                        : 'border-slate-100 text-slate-500 hover:border-slate-200'}`}
                    style={travelMethod === value ? { background: color, borderColor: color } : {}}
                  >
                    <Icon className="w-5 h-5" />
                    {label}
                  </button>
                ))}
              </div>
              {travelMethod === 'excursion' && trip?.category === 'Europe Trip' && (
                <p className="text-xs text-amber-600">
                  Excursion lift support is available for Europe only for now. Cable car, gondola, and similar lift stations will use the Europe lift dataset when available.
                </p>
              )}
            </div>
          )}

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
            <PlaceSearch
              label="Search place (auto-fill all fields)"
              onSelect={handlePlaceSelect}
              travelMethod={travelMethod}
              country={(form.country || '').trim()}
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
                      place_name: '',
                      city: '',
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
                {travelMethod === 'train'
                  ? 'Train locations must be selected from train station search or snapped from the map. Changing country resets the selection.'
                  : `This ${travelMethod} stop should be selected from search or snapped to the nearest ${SNAP_METHOD_LABELS[travelMethod]}. Changing country resets the selection.`}
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
              min={editMinVisitDate || undefined}
              max={editMaxVisitDate || undefined}
            />
            {dateError ? (
              <p className="text-xs text-red-500 -mt-2">{dateError}</p>
            ) : (
              editMinVisitDate && editMaxVisitDate && (
                <p className="text-xs text-slate-400 -mt-2">
                  This location date must stay between {editMinVisitDate} and {editMaxVisitDate} to preserve timeline order.
                </p>
              )
            )}
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-slate-700">Description</label>
              <textarea
                value={form.description}
                onChange={set('description')}
                rows={3}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
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
              isLoading={snappingTransportPlace}
              loadingText={isSnapMethod
                ? `Finding the nearest ${SNAP_METHOD_LABELS[travelMethod]}...`
                : 'Identifying this location...'}
              helperText={isSnapMethod
                ? (snappingTransportPlace
                  ? `Finding the nearest ${SNAP_METHOD_LABELS[travelMethod]}...`
                  : `Click on the map and wait until it snaps to a ${SNAP_METHOD_LABELS[travelMethod]}`)
                : 'Click on the map to place a pin and auto-fill the location'}
            />
          </div>

          <div className="flex gap-3">
            <Button
              type="submit"
              loading={saving}
              disabled={saving || uploading || snappingTransportPlace || (isSnapMethod && !trainStation)}
              className="flex-1"
              size="lg"
            >
              Save changes
            </Button>
            <Link
              to={`/trips/${tripId}`}
              onClick={(event) => {
                if (saving) event.preventDefault()
              }}
              className={saving ? 'pointer-events-none' : ''}
              aria-disabled={saving}
            >
              <Button type="button" variant="secondary" size="lg" disabled={saving}>Cancel</Button>
            </Link>
          </div>
        </form>
      </div>
    </Layout>
  )
}
