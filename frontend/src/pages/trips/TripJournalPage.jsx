import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Check, RefreshCw, Save, Sparkles } from 'lucide-react'
import toast from 'react-hot-toast'

import { tripsApi } from '../../api/trips'
import Modal from '../../components/ui/Modal'
import Layout from '../../components/layout/Layout'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import JournalRenderer from '../../components/journal/JournalRenderer'

const TONES = ['warm', 'reflective', 'adventurous', 'elegant']
const LENGTHS = ['short', 'standard', 'detailed']
const TEMPLATES = [
  {
    key: 'editorial',
    name: 'Editorial',
    eyebrow: 'Magazine spread',
    description: 'Large cover image, polished chapter cards, and a refined travel feature look.',
  },
  {
    key: 'scrapbook',
    name: 'Scrapbook',
    eyebrow: 'Memory collage',
    description: 'Layered photo cards, pinned notes, and a more personal keepsake feeling.',
  },
  {
    key: 'field_notes',
    name: 'Field Notes',
    eyebrow: 'Expedition log',
    description: 'Bold route panels, destination facts, and a travel notebook layout.',
  },
]

export default function TripJournalPage() {
  const { tripId } = useParams()
  const navigate = useNavigate()
  const [trip, setTrip] = useState(null)
  const [journal, setJournal] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [tone, setTone] = useState('warm')
  const [lengthMode, setLengthMode] = useState('standard')
  const [useAi, setUseAi] = useState(true)
  const [templateKey, setTemplateKey] = useState('editorial')
  const [generateModalOpen, setGenerateModalOpen] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const tripData = await tripsApi.get(tripId)
      setTrip(tripData)
      try {
        const journalData = await tripsApi.getJournal(tripId)
        setJournal(journalData)
        setTone(journalData.tone || 'warm')
        setLengthMode(journalData.length_mode || 'standard')
        setTemplateKey(journalData.content_json?.template_key || 'editorial')
      } catch {
        setJournal(null)
      }
    } catch {
      navigate('/trips')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [tripId])

  const applyTemplate = (nextTemplateKey) => {
    setTemplateKey(nextTemplateKey)
    if (!journal) return
    setJournal({
      ...journal,
      content_json: {
        ...(journal.content_json || {}),
        template_key: nextTemplateKey,
      },
    })
  }

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const journalData = await tripsApi.generateJournal(tripId, {
        tone,
        length_mode: lengthMode,
        use_ai: useAi,
        template_key: templateKey,
      })
      setJournal(journalData)
      setGenerateModalOpen(false)
      const providerLabel = journalData.content_json?.provider_label
      toast.success(providerLabel ? `Travel journal generated with ${providerLabel}` : 'Travel journal generated')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not generate journal')
    } finally {
      setGenerating(false)
    }
  }

  const handleSave = async () => {
    if (!journal) return
    setSaving(true)
    try {
      const saved = await tripsApi.updateJournal(tripId, {
        title: journal.title,
        intro_text: journal.intro_text,
        closing_text: journal.closing_text,
        tone,
        length_mode: lengthMode,
        content_json: {
          ...(journal.content_json || {}),
          template_key: journal.content_json?.template_key || templateKey,
        },
      })
      setJournal(saved)
      setTemplateKey(saved.content_json?.template_key || templateKey)
      toast.success('Travel journal saved')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not save journal')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Layout><div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div></Layout>
  if (!trip) return null

  return (
    <Layout>
      <div className="space-y-6 journal-page-shell">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <Link to={`/trips/${tripId}`} className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-primary-600 mb-3">
              <ArrowLeft className="w-4 h-4" /> Back to trip
            </Link>
            <h1 className="text-2xl font-bold text-slate-900">Travel Journal</h1>
            <p className="mt-1 text-sm text-slate-500">
              Shape your route, notes, images, and trip details into a more editorial travel diary.
            </p>
          </div>
          {trip.visibility !== 'private' && trip.share_slug ? (
            <Link to={`/shared/${trip.share_slug}/journal`} className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
              Open public journal
            </Link>
          ) : null}
        </div>

        <div className="overflow-hidden rounded-[2rem] border border-[#e7dccb] bg-[linear-gradient(135deg,rgba(255,255,255,0.98),rgba(248,250,252,0.95)_36%,rgba(255,247,236,0.98))] p-5 shadow-[0_18px_54px_rgba(148,163,184,0.12)]">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Journal Studio</p>
              <p className="mt-2 text-lg font-semibold text-slate-900">Create a warmer, more memorable diary page for this trip.</p>
              <p className="mt-2 max-w-2xl text-sm text-slate-500">
                Pick a visual template, tune the tone and length, let Gemini help draft the prose when available, then refine the story before saving.
              </p>
              {journal?.content_json?.provider_label ? (
                <p className="mt-2 text-xs text-slate-400">Latest generation source: {journal.content_json.provider_label}</p>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setGenerateModalOpen(true)}
                className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
              >
                <Sparkles className="h-4 w-4" />
                {journal ? 'Regenerate journal' : 'Create journal'}
              </button>
              {journal ? (
                <>
                  <button
                    type="button"
                    onClick={handleSave}
                    className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
                    disabled={saving}
                  >
                    <Save className="h-4 w-4" />
                    Save edits
                  </button>
                </>
              ) : null}
            </div>
          </div>
          {journal ? (
            <div className="mt-5 border-t border-[#eadfce] pt-5">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-700">Template style</p>
                  <p className="mt-1 text-xs text-slate-500">
                    Switch the journal look anytime. Your story text stays the same unless you regenerate.
                  </p>
                </div>
                <p className="text-xs uppercase tracking-[0.24em] text-slate-400">
                  Current: {TEMPLATES.find((template) => template.key === templateKey)?.name || 'Editorial'}
                </p>
              </div>
              <div className="mt-4 grid gap-3 xl:grid-cols-3">
                {TEMPLATES.map((template) => {
                  const active = template.key === templateKey
                  return (
                    <button
                      key={`studio-${template.key}`}
                      type="button"
                      onClick={() => applyTemplate(template.key)}
                      className={`journal-template-option text-left ${active ? 'journal-template-option-active' : ''}`}
                    >
                      <span className={`journal-template-swatch journal-template-swatch-${template.key}`} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">{template.eyebrow}</span>
                        <span className="mt-1 block text-base font-semibold text-slate-900">{template.name}</span>
                        <span className="mt-1 block text-sm leading-6 text-slate-500">{template.description}</span>
                      </span>
                      <span className={`journal-template-check ${active ? 'journal-template-check-active' : ''}`}>
                        <Check className="h-4 w-4" />
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          ) : null}
          {!trip.description ? (
            <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              This trip has limited written notes. The journal can still be created from your timeline, companions, route flow, and uploaded photos.
            </p>
          ) : null}
        </div>

        {generating && !journal ? (
          <div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div>
        ) : journal ? (
          <div className="print-journal-page">
            <JournalRenderer trip={trip} journal={journal} editable onChange={setJournal} showProviderLabel />
          </div>
        ) : (
          <div className="rounded-2xl border border-slate-100 bg-white px-6 py-16 text-center text-slate-400 shadow-sm">
            No journal has been generated for this trip yet.
          </div>
        )}
      </div>

      <Modal
        open={generateModalOpen}
        onClose={() => !generating && setGenerateModalOpen(false)}
        title={journal ? 'Regenerate Travel Journal' : 'Create Travel Journal'}
        size="md"
      >
        <div className="space-y-5">
          <p className="text-sm text-slate-500">
            Create a richer journal draft from your route, timeline notes, images, and trip details. When Gemini is configured, it will write a more natural story draft and fall back safely if the AI service is unavailable.
          </p>
          <div className="space-y-3">
            <div>
              <p className="text-sm font-medium text-slate-700">Template</p>
              <p className="mt-1 text-xs text-slate-500">Choose the overall visual style before generating the journal.</p>
            </div>
            <div className="grid gap-3">
              {TEMPLATES.map((template) => {
                const active = template.key === templateKey
                return (
                  <button
                    key={template.key}
                    type="button"
                    onClick={() => applyTemplate(template.key)}
                    className={`journal-template-option text-left ${active ? 'journal-template-option-active' : ''}`}
                  >
                    <span className={`journal-template-swatch journal-template-swatch-${template.key}`} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">{template.eyebrow}</span>
                      <span className="mt-1 block text-base font-semibold text-slate-900">{template.name}</span>
                      <span className="mt-1 block text-sm leading-6 text-slate-500">{template.description}</span>
                    </span>
                    <span className={`journal-template-check ${active ? 'journal-template-check-active' : ''}`}>
                      <Check className="h-4 w-4" />
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm text-slate-600">
              Tone
              <select value={tone} onChange={(event) => setTone(event.target.value)} className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
                {TONES.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm text-slate-600">
              Length
              <select value={lengthMode} onChange={(event) => setLengthMode(event.target.value)} className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
                {LENGTHS.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
          </div>
          <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={useAi}
              onChange={(event) => setUseAi(event.target.checked)}
              className="mt-1 h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
            />
              <span>
              <span className="font-medium text-slate-800">Use Gemini journal writing when available</span>
              <br />
              If Gemini is configured on the backend, it will generate more natural prose. Otherwise the app falls back to the built-in structured draft.
            </span>
          </label>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setGenerateModalOpen(false)}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
              disabled={generating}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleGenerate}
              className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
              disabled={generating}
            >
              <RefreshCw className={`h-4 w-4 ${generating ? 'animate-spin' : ''}`} />
              {generating ? 'Generating...' : (journal ? 'Regenerate now' : 'Generate now')}
            </button>
          </div>
        </div>
      </Modal>
    </Layout>
  )
}
