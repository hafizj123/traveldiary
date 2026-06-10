import { useState, useCallback, useEffect, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Upload, MapPin } from 'lucide-react'
import { useDropzone } from 'react-dropzone'
import { timelineApi } from '../../api/timeline'
import { uploadApi } from '../../api/upload'
import { tripsApi } from '../../api/trips'
import Layout from '../../components/layout/Layout'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'
import MapPicker from '../../components/map/MapPicker'
import PlaceSearch from '../../components/ui/PlaceSearch'
import { TRAVEL_METHODS } from '../../utils/travelIcons'
import { getVisitDateRangeError, isVisitDateWithinTripRange } from '../../utils/visitDate'
import toast from 'react-hot-toast'

export default function AddPointPage() {
  const { tripId } = useParams()
  const navigate = useNavigate()

  const [trip, setTrip] = useState(null)
  const [form, setForm] = useState({
    country: '', city: '', place_name: '', description: '',
    visit_date: '', latitude: '', longitude: '',
    image_url: '', travel_method: '',
  })
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState(null)

  const uploadedUrlRef = useRef(null)
  const submittedRef = useRef(false)

  useEffect(() => {
    return () => {
      if (!submittedRef.current && uploadedUrlRef.current && localStorage.getItem('token')) {
        uploadApi.deleteImage(uploadedUrlRef.current).catch(() => {})
      }
    }
  }, [])

  useEffect(() => {
    tripsApi.get(tripId).then(setTrip).catch(() => {})
  }, [tripId])

  const set = (key) => (e) => setForm((current) => ({ ...current, [key]: e.target.value }))

  const handlePlaceSelect = ({ place_name, city, country, latitude, longitude }) => {
    setForm((current) => ({
      ...current,
      place_name: place_name || current.place_name,
      city: city || current.city,
      country: country || current.country,
      latitude,
      longitude,
    }))
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
    setForm((current) => ({ ...current, latitude: lat, longitude: lon }))
  }

  const dateError = getVisitDateRangeError(form.visit_date, trip)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (dateError) {
      toast.error(dateError)
      return
    }

    setLoading(true)
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
        travel_method: form.travel_method || null,
      }
      await timelineApi.addPoint(tripId, payload)
      submittedRef.current = true
      toast.success('Location added!')
      navigate(`/trips/${tripId}`)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to add location')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Layout>
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <Link to={`/trips/${tripId}`} className="p-2 hover:bg-slate-100 rounded-lg">
            <ArrowLeft className="w-5 h-5 text-slate-500" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Add Location</h1>
            {trip && (trip.start_date || trip.end_date) && (
              <p className="text-xs text-slate-400 mt-0.5">
                Trip date range: {trip.start_date || '-'} to {trip.end_date || '-'}
              </p>
            )}
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-3">
            <h2 className="font-semibold text-slate-700">How did you get here?</h2>
            <div className="grid grid-cols-3 sm:grid-cols-7 gap-2">
              {TRAVEL_METHODS.map(({ value, label, Icon, color }) => (
                <button
                  key={value}
                  type="button"
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
              {uploading && <p className="text-primary-500 text-sm mt-2">Uploading...</p>}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-4">
            <h2 className="font-semibold text-slate-700">Place details</h2>

            <PlaceSearch
              label="Search place (auto-fill all fields)"
              onSelect={handlePlaceSelect}
              travelMethod={form.travel_method || ''}
            />

            <div className="border-t border-slate-50 pt-4 grid grid-cols-2 gap-4">
              <Input label="Country *" value={form.country} onChange={set('country')} required placeholder="Switzerland" />
              <Input label="City" value={form.city} onChange={set('city')} placeholder="Lauterbrunnen" />
            </div>
            <Input label="Place name *" value={form.place_name} onChange={set('place_name')} required placeholder="Lauterbrunnen Valley" />

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
              <Input label="Latitude" type="number" step="any" value={form.latitude} onChange={set('latitude')} placeholder="46.5935" />
              <Input label="Longitude" type="number" step="any" value={form.longitude} onChange={set('longitude')} placeholder="7.9091" />
            </div>
            <MapPicker lat={form.latitude} lon={form.longitude} onChange={handleMapPick} />
          </div>

          <div className="flex gap-3">
            <Button type="submit" loading={loading} className="flex-1" size="lg">Add location</Button>
            <Link to={`/trips/${tripId}`}>
              <Button type="button" variant="secondary" size="lg">Cancel</Button>
            </Link>
          </div>
        </form>
      </div>
    </Layout>
  )
}
