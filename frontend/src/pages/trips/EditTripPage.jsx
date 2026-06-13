import { useState, useEffect } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { tripsApi } from '../../api/trips'
import { uploadApi } from '../../api/upload'
import Layout from '../../components/layout/Layout'
import Button from '../../components/ui/Button'
import Input  from '../../components/ui/Input'
import PlaceSearch from '../../components/ui/PlaceSearch'
import CountryMultiSelect from '../../components/ui/CountryMultiSelect'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import toast from 'react-hot-toast'
import { validateTripForm } from '../../utils/tripForm'

export default function EditTripPage() {
  const { tripId } = useParams()
  const navigate   = useNavigate()
  const [form, setForm] = useState(null)
  const [loading, setLoading]   = useState(true)
  const [saving, setSaving]     = useState(false)
  const [uploading, setUploading] = useState(false)
  const [errors, setErrors] = useState({})

  useEffect(() => {
    tripsApi.get(tripId).then(t => {
      setForm({
        title:           t.title,
        description:     t.description || '',
        start_date:      t.start_date || '',
        end_date:        t.end_date   || '',
        starting_place_name: t.starting_place_name || '',
        starting_city: t.starting_city || '',
        starting_country: t.starting_country || '',
        starting_latitude: t.starting_latitude ?? '',
        starting_longitude: t.starting_longitude ?? '',
        planned_countries: t.planned_countries || [],
        cover_image_url: t.cover_image_url || '',
        visibility:      t.visibility,
      })
    }).catch(() => navigate('/trips'))
     .finally(() => setLoading(false))
  }, [tripId])

  const set = (k) => (e) => {
    const value = e.target.value
    setForm(f => ({ ...f, [k]: value }))
    setErrors(prev => ({
      ...prev,
      [k]: undefined,
      ...(k === 'start_date' ? { end_date: undefined } : {}),
      ...(k === 'end_date' ? { start_date: undefined } : {}),
    }))
  }

  const handleCoverUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const res = await uploadApi.image(file)
      setForm(f => ({ ...f, cover_image_url: res.url }))
      toast.success('Cover updated')
    } catch (err) { toast.error(err.message || 'Upload failed') }
    finally  { setUploading(false) }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const { errors: nextErrors, sanitized } = validateTripForm(form)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) return

    setSaving(true)
    try {
      await tripsApi.update(tripId, {
        ...sanitized,
        start_date: sanitized.start_date,
        end_date: sanitized.end_date,
        starting_latitude: Number(sanitized.starting_latitude),
        starting_longitude: Number(sanitized.starting_longitude),
        cover_image_url: sanitized.cover_image_url || null,
      })
      toast.success('Trip updated')
      navigate(`/trips/${tripId}`)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update')
    } finally { setSaving(false) }
  }

  if (loading || !form) return <Layout><div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div></Layout>

  return (
    <Layout>
      <div className="max-w-xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <Link to={`/trips/${tripId}`} className="p-2 hover:bg-slate-100 rounded-lg">
            <ArrowLeft className="w-5 h-5 text-slate-500" />
          </Link>
          <h1 className="text-2xl font-bold text-slate-800">Edit Trip</h1>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-5">
          <Input label="Trip title *" value={form.title} onChange={set('title')} required error={errors.title} />
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-slate-700">Description</label>
            <textarea value={form.description} onChange={set('description')} rows={3}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input label="Start date *" type="date" value={form.start_date} onChange={set('start_date')} required error={errors.start_date} max={form.end_date || undefined} />
            <Input label="End date *"   type="date" value={form.end_date}   onChange={set('end_date')} required error={errors.end_date} min={form.start_date || undefined} />
          </div>
          <div className="space-y-3 rounded-xl border border-slate-100 bg-slate-50/80 p-4">
            <h2 className="text-sm font-semibold text-slate-700">Starting place *</h2>
            <PlaceSearch
              label="Search starting place"
              onSelect={({ place_name, city, country, latitude, longitude }) => {
                setForm((current) => ({
                  ...current,
                  starting_place_name: place_name || '',
                  starting_city: city || '',
                  starting_country: country || '',
                  starting_latitude: latitude ?? '',
                  starting_longitude: longitude ?? '',
                  planned_countries: Array.from(new Set([...(current.planned_countries || []), country || ''].filter(Boolean))),
                }))
                setErrors((prev) => ({
                  ...prev,
                  starting_place_name: undefined,
                  starting_country: undefined,
                  planned_countries: undefined,
                }))
                toast.success('Starting place updated')
              }}
              placeholder="Search where the trip started"
            />
            <Input label="Starting place" value={form.starting_place_name} onChange={set('starting_place_name')} required error={errors.starting_place_name} />
            <div className="grid grid-cols-2 gap-4">
              <Input label="Starting country" value={form.starting_country} onChange={set('starting_country')} required error={errors.starting_country} />
              <Input label="Starting city" value={form.starting_city} onChange={set('starting_city')} />
            </div>
          </div>
          <CountryMultiSelect
            label="Countries in this trip *"
            value={form.planned_countries}
            onChange={(planned_countries) => {
              setForm((current) => ({ ...current, planned_countries }))
              setErrors((prev) => ({ ...prev, planned_countries: undefined }))
            }}
            error={errors.planned_countries}
          />
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-slate-700">Cover image</label>
            {form.cover_image_url && <img src={form.cover_image_url} alt="cover" className="w-full h-32 object-cover rounded-lg mb-2" />}
            <input type="file" accept="image/*" onChange={handleCoverUpload} className="text-sm text-slate-500" />
            {uploading && (
              <p className="inline-flex items-center gap-2 text-xs text-primary-500">
                <LoadingSpinner size="xs" />
                Uploading...
              </p>
            )}
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-slate-700">Visibility</label>
            <select value={form.visibility} onChange={set('visibility')}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500">
              <option value="private">Private</option>
              <option value="public">Public (shareable)</option>
            </select>
          </div>
          <div className="flex gap-3 pt-2">
            <Button type="submit" loading={saving} className="flex-1">Save changes</Button>
            <Link to={`/trips/${tripId}`}><Button type="button" variant="secondary">Cancel</Button></Link>
          </div>
        </form>
      </div>
    </Layout>
  )
}
