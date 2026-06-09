import { useState, useEffect } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { tripsApi } from '../../api/trips'
import { uploadApi } from '../../api/upload'
import Layout from '../../components/layout/Layout'
import Button from '../../components/ui/Button'
import Input  from '../../components/ui/Input'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import toast from 'react-hot-toast'

export default function EditTripPage() {
  const { tripId } = useParams()
  const navigate   = useNavigate()
  const [form, setForm] = useState(null)
  const [loading, setLoading]   = useState(true)
  const [saving, setSaving]     = useState(false)
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    tripsApi.get(tripId).then(t => {
      setForm({
        title:           t.title,
        description:     t.description || '',
        start_date:      t.start_date || '',
        end_date:        t.end_date   || '',
        cover_image_url: t.cover_image_url || '',
        visibility:      t.visibility,
      })
    }).catch(() => navigate('/trips'))
     .finally(() => setLoading(false))
  }, [tripId])

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const handleCoverUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const res = await uploadApi.image(file)
      setForm(f => ({ ...f, cover_image_url: res.url }))
      toast.success('Cover updated')
    } catch { toast.error('Upload failed') }
    finally  { setUploading(false) }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await tripsApi.update(tripId, {
        ...form,
        start_date:      form.start_date      || null,
        end_date:        form.end_date        || null,
        cover_image_url: form.cover_image_url || null,
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
          <Input label="Trip title *" value={form.title} onChange={set('title')} required />
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-slate-700">Description</label>
            <textarea value={form.description} onChange={set('description')} rows={3}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input label="Start date" type="date" value={form.start_date} onChange={set('start_date')} />
            <Input label="End date"   type="date" value={form.end_date}   onChange={set('end_date')} />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-slate-700">Cover image</label>
            {form.cover_image_url && <img src={form.cover_image_url} alt="cover" className="w-full h-32 object-cover rounded-lg mb-2" />}
            <input type="file" accept="image/*" onChange={handleCoverUpload} className="text-sm text-slate-500" />
            {uploading && <p className="text-xs text-primary-500">Uploading…</p>}
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
