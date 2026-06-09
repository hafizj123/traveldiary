import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Upload } from 'lucide-react'
import { useDropzone } from 'react-dropzone'
import { timelineApi } from '../../api/timeline'
import { uploadApi } from '../../api/upload'
import { tripsApi } from '../../api/trips'
import Layout from '../../components/layout/Layout'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'
import MapPicker from '../../components/map/MapPicker'
import PlaceSearch from '../../components/ui/PlaceSearch'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import { TRAVEL_METHODS } from '../../utils/travelIcons'
import { getVisitDateRangeError } from '../../utils/visitDate'
import toast from 'react-hot-toast'

export default function EditPointPage() {
  const { tripId, pointId } = useParams()
  const navigate = useNavigate()

  const [trip, setTrip] = useState(null)
  const [form, setForm] = useState(null)
  const [travelMethod, setTravelMethod] = useState('')
  const [incomingSegment, setIncomingSegment] = useState(null)
  const [prevPointId, setPrevPointId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [preview, setPreview] = useState(null)
  const [uploading, setUploading] = useState(false)

  const originalUrlRef = useRef(null)
  const newlyUploadedRef = useRef(null)
  const submittedRef = useRef(false)

  useEffect(() => {
    return () => {
      if (!submittedRef.current && newlyUploadedRef.current && localStorage.getItem('token')) {
        uploadApi.deleteImage(newlyUploadedRef.current).catch(() => {})
      }
    }
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

      const seg = segs.find((segment) => segment.to_point_id === parseInt(pointId, 10))
      if (seg) {
        setIncomingSegment(seg)
        setTravelMethod(seg.travel_method || '')
      }

      const sorted = [...pts].sort((a, b) => a.sequence_no - b.sequence_no)
      const idx = sorted.findIndex((point) => point.id === parseInt(pointId, 10))
      if (idx > 0) setPrevPointId(sorted[idx - 1].id)
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
      toast.success('Photo updated')
    } catch {
      toast.error('Upload failed')
    } finally {
      setUploading(false)
    }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/*': [] },
    maxFiles: 1,
  })

  const dateError = form ? getVisitDateRangeError(form.visit_date, trip) : ''

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (dateError) {
      toast.error(dateError)
      return
    }

    setSaving(true)
    try {
      await timelineApi.updatePoint(pointId, {
        ...form,
        latitude: form.latitude !== '' ? parseFloat(form.latitude) : null,
        longitude: form.longitude !== '' ? parseFloat(form.longitude) : null,
        city: form.city || null,
        description: form.description || null,
        image_url: form.image_url || null,
      })

      if (travelMethod && incomingSegment) {
        if (travelMethod !== incomingSegment.travel_method) {
          await timelineApi.updateSegment(incomingSegment.id, { travel_method: travelMethod })
        }
      } else if (travelMethod && prevPointId && !incomingSegment) {
        await timelineApi.createSegment(tripId, {
          from_point_id: prevPointId,
          to_point_id: parseInt(pointId, 10),
          travel_method: travelMethod,
        })
      }

      submittedRef.current = true
      if (
        newlyUploadedRef.current &&
        originalUrlRef.current &&
        newlyUploadedRef.current !== originalUrlRef.current
      ) {
        uploadApi.deleteImage(originalUrlRef.current).catch(() => {})
      }
      toast.success('Location updated')
      navigate(`/trips/${tripId}`)
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

        <form onSubmit={handleSubmit} className="space-y-5">
          {prevPointId && (
            <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-3">
              <h2 className="font-semibold text-slate-700">How did you get here?</h2>
              <div className="grid grid-cols-3 sm:grid-cols-7 gap-2">
                {TRAVEL_METHODS.map(({ value, label, Icon, color }) => (
                  <button
                    key={value}
                    type="button"
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
            </div>
          )}

          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-3">
            <h2 className="font-semibold text-slate-700">Photo</h2>
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors
                ${isDragActive ? 'border-primary-400 bg-primary-50' : 'border-slate-200 hover:border-primary-300'}`}
            >
              <input {...getInputProps()} />
              {preview ? (
                <img src={preview} alt="preview" className="max-h-40 mx-auto rounded-lg object-cover" />
              ) : (
                <div className="text-slate-400 space-y-1">
                  <Upload className="w-7 h-7 mx-auto" />
                  <p className="text-sm">Drop or click to change photo</p>
                </div>
              )}
              {uploading && <p className="text-primary-500 text-sm mt-2">Uploading...</p>}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-4">
            <PlaceSearch
              label="Search to change location"
              onSelect={({ place_name, city, country, latitude, longitude }) => {
                setForm((current) => ({
                  ...current,
                  place_name,
                  city: city || current.city,
                  country: country || current.country,
                  latitude,
                  longitude,
                }))
                toast.success('Location auto-filled!')
              }}
              travelMethod={travelMethod}
            />
            <div className="border-t border-slate-50 pt-4 grid grid-cols-2 gap-4">
              <Input label="Country *" value={form.country} onChange={set('country')} required />
              <Input label="City" value={form.city} onChange={set('city')} />
            </div>
            <Input label="Place name *" value={form.place_name} onChange={set('place_name')} required />
            <Input
              label="Visit date *"
              type="date"
              value={form.visit_date}
              onChange={set('visit_date')}
              required
              min={trip?.start_date || undefined}
              max={trip?.end_date || undefined}
            />
            {dateError ? (
              <p className="text-xs text-red-500 -mt-2">{dateError}</p>
            ) : (
              trip?.start_date && trip?.end_date && (
                <p className="text-xs text-slate-400 -mt-2">
                  Only dates within the trip range ({trip.start_date} to {trip.end_date}) are allowed
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
            <h2 className="font-semibold text-slate-700">Location</h2>
            <div className="grid grid-cols-2 gap-4">
              <Input label="Latitude" type="number" step="any" value={form.latitude} onChange={set('latitude')} />
              <Input label="Longitude" type="number" step="any" value={form.longitude} onChange={set('longitude')} />
            </div>
            <MapPicker
              lat={form.latitude}
              lon={form.longitude}
              onChange={(lat, lon) => setForm((current) => ({ ...current, latitude: lat, longitude: lon }))}
            />
          </div>

          <div className="flex gap-3">
            <Button type="submit" loading={saving} className="flex-1" size="lg">Save changes</Button>
            <Link to={`/trips/${tripId}`}>
              <Button type="button" variant="secondary" size="lg">Cancel</Button>
            </Link>
          </div>
        </form>
      </div>
    </Layout>
  )
}
