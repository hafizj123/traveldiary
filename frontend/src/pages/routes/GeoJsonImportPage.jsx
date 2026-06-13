import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, Database, Download, Plane, RefreshCcw, ShieldAlert, TrainFront } from 'lucide-react'

import Layout from '../../components/layout/Layout'
import Button from '../../components/ui/Button'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import SearchableLocationInput from '../../components/ui/SearchableLocationInput'
import { searchCities, searchCountries } from '../../components/ui/locationSearch'
import { routesApi } from '../../api/routes'
import { useAuth } from '../../contexts/AuthContext'

const ADMIN_EMAIL = 'hafiz.shadowfiend@gmail.com'
const LARGE_RAIL_COUNTRY_KEYS = new Set([
  'china',
  'united states',
  'united states of america',
  'usa',
  'us',
  'russia',
  'russian federation',
  'india',
])

function normalizeChinaCityName(value) {
  return (value || '')
    .replace(/\s*\((city|municipality)\)\s*$/i, '')
    .replace(/\s+(city|municipality)\s*$/i, '')
    .replace(/\s+shi\s*$/i, '')
    .trim()
}

function normalizeCountryKey(value) {
  return (value || '').trim().toLowerCase()
}

function railImportNeedsSubdivision(countryName) {
  return LARGE_RAIL_COUNTRY_KEYS.has(normalizeCountryKey(countryName))
}

function StatusBadge({ status }) {
  const styles = {
    queued: 'bg-amber-100 text-amber-700',
    running: 'bg-sky-100 text-sky-700',
    completed: 'bg-emerald-100 text-emerald-700',
    failed: 'bg-rose-100 text-rose-700',
  }

  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${styles[status] || 'bg-slate-100 text-slate-600'}`}>
      {status || 'unknown'}
    </span>
  )
}

function isExistingFileError(detail) {
  return typeof detail === 'string' && detail.toLowerCase().includes('geojson file already exists')
}

function OverwriteConfirmModal({ open, message, onConfirm, onCancel, loading }) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-slate-900/45 px-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <div className="mb-3 flex items-center gap-2 text-amber-600">
          <AlertTriangle className="h-5 w-5" />
          <h2 className="text-lg font-semibold text-slate-800">File Already Exists</h2>
        </div>
        <p className="text-sm leading-relaxed text-slate-500">
          {message}
        </p>
        <p className="mt-2 text-sm leading-relaxed text-slate-500">
          Confirm to replace it with a fresh import, or cancel to keep the current file.
        </p>
        <div className="mt-5 flex gap-3">
          <Button type="button" variant="secondary" className="flex-1" onClick={onCancel} disabled={loading}>
            Cancel
          </Button>
          <Button type="button" className="flex-1" onClick={onConfirm} loading={loading}>
            Confirm
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function GeoJsonImportPage() {
  const { user } = useAuth()
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [importType, setImportType] = useState('rail')
  const [countryName, setCountryName] = useState('')
  const [countryIsoCode, setCountryIsoCode] = useState('')
  const [cityName, setCityName] = useState('')
  const [cityConfirmed, setCityConfirmed] = useState(false)
  const [tasks, setTasks] = useState([])
  const [error, setError] = useState('')
  const [overwritePrompt, setOverwritePrompt] = useState(null)

  const isAllowed = (user?.email || '').toLowerCase() === ADMIN_EMAIL
  const normalizedCountryName = countryName.trim().toLowerCase()
  const isAirportImport = importType === 'airport'
  const requiresRailSubdivision = !isAirportImport && railImportNeedsSubdivision(countryName)
  const isChinaSelected = normalizedCountryName === 'china'
  const hasValidCountrySelection = isAirportImport ? !!countryName.trim() : (requiresRailSubdivision ? cityConfirmed : !!countryName.trim())
  const hasValidAirportIso = !isAirportImport || /^[A-Z]{2}$/.test(countryIsoCode.trim().toUpperCase())
  const activeTask = useMemo(
    () => tasks.find((task) => task.status === 'queued' || task.status === 'running') || null,
    [tasks],
  )
  const canStartImport = hasValidCountrySelection && hasValidAirportIso && (!requiresRailSubdivision || (cityName.trim() && cityConfirmed)) && !submitting && !activeTask

  useEffect(() => {
    if (!isAllowed) {
      setLoading(false)
      return
    }

    let cancelled = false

    const loadTasks = async (background = false) => {
      if (!background) setLoading(true)
      try {
        const data = await routesApi.geojsonImportTasks()
        if (!cancelled) {
          setTasks(data.items || [])
          setError('')
        }
      } catch (err) {
        if (!cancelled) {
          setError(err?.response?.data?.detail || 'Failed to load GeoJSON tasks.')
        }
      } finally {
        if (!cancelled && !background) setLoading(false)
      }
    }

    loadTasks()

    return () => {
      cancelled = true
    }
  }, [isAllowed])

  useEffect(() => {
    if (!isAllowed || !activeTask) return undefined

    let cancelled = false
    const pollId = window.setInterval(async () => {
      try {
        const data = await routesApi.geojsonImportTasks()
        if (!cancelled) {
          setTasks(data.items || [])
          setError('')
        }
      } catch (err) {
        if (!cancelled) {
          setError(err?.response?.data?.detail || 'Failed to load GeoJSON tasks.')
        }
      }
    }, 4000)

    return () => {
      cancelled = true
      window.clearInterval(pollId)
    }
  }, [activeTask, isAllowed])

  const startImport = async ({ overwrite = false, payloadOverride = null } = {}) => {
    const trimmed = (payloadOverride?.country_name || countryName).trim()
    const type = payloadOverride?.import_type || importType
    if (!trimmed) {
      setError('Country name is required.')
      return
    }
    const trimmedCity = (payloadOverride?.city_name || cityName).trim()
    const iso = (payloadOverride?.iso_code || countryIsoCode).trim().toUpperCase()
    if (type === 'rail' && railImportNeedsSubdivision(trimmed) && !trimmedCity) {
      setError('City or region name is required for this country.')
      return
    }
    if (type === 'rail' && railImportNeedsSubdivision(trimmed) && !cityConfirmed && !payloadOverride) {
      setError('Pick a city or region from the dropdown before starting the import.')
      return
    }
    if (type === 'airport' && !/^[A-Z]{2}$/.test(iso)) {
      setError('Airport imports require a 2-letter ISO country code, such as KH or MY.')
      return
    }

    const payload = payloadOverride || {
      country_name: trimmed,
      city_name: type === 'rail' && railImportNeedsSubdivision(trimmed) ? trimmedCity : null,
      import_type: type,
      iso_code: type === 'airport' ? iso : null,
    }

    setSubmitting(true)
    try {
      const data = await routesApi.createGeojsonImportTask({ ...payload, overwrite })
      setTasks((current) => [data.task, ...current])
      setCountryName('')
      setCountryIsoCode('')
      setCityName('')
      setCityConfirmed(false)
      setOverwritePrompt(null)
      setError('')
    } catch (err) {
      const detail = err?.response?.data?.detail
      if (!overwrite && isExistingFileError(detail)) {
        setOverwritePrompt({ message: detail, payload })
        setError('')
      } else {
        setError(detail || 'Failed to create GeoJSON import task.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    await startImport()
  }

  if (loading) {
    return <Layout><div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div></Layout>
  }

  if (!isAllowed) {
    return (
      <Layout>
        <div className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <ShieldAlert className="mx-auto mb-4 h-10 w-10 text-slate-300" />
          <h1 className="text-xl font-semibold text-slate-800">Access Restricted</h1>
          <p className="mt-2 text-sm text-slate-500">This GeoJSON import tool is only available to the admin account.</p>
        </div>
      </Layout>
    )
  }

  return (
    <Layout>
      <OverwriteConfirmModal
        open={!!overwritePrompt}
        message={overwritePrompt?.message || ''}
        loading={submitting}
        onCancel={() => setOverwritePrompt(null)}
        onConfirm={() => startImport({ overwrite: true, payloadOverride: overwritePrompt?.payload })}
      />
      <div className="space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <Link to="/dashboard" className="mb-2 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-primary-600">
              <ArrowLeft className="h-4 w-4" /> Dashboard
            </Link>
            <h1 className="text-2xl font-bold text-slate-800">GeoJSON Import Tasks</h1>
            <p className="text-sm text-slate-500">
              Pull rail, station, and airport data from Overpass, save it into the backend GeoJSON folder, and keep imports strictly one at a time.
            </p>
          </div>
          <button
            type="button"
            onClick={async () => {
              const data = await routesApi.geojsonImportTasks()
              setTasks(data.items || [])
            }}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
          >
            <RefreshCcw className="h-4 w-4" />
            Refresh
          </button>
        </div>

        <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
          <div className="space-y-5">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-800">
                <Download className="h-4 w-4 text-primary-600" />
                New Import
              </div>
              <form onSubmit={handleSubmit} className="space-y-3">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">Import type</label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { value: 'rail', label: 'Rail data', Icon: TrainFront },
                      { value: 'airport', label: 'Airports', Icon: Plane },
                    ].map(({ value, label, Icon }) => (
                      <button
                        key={value}
                        type="button"
                        disabled={submitting || !!activeTask}
                        onClick={() => {
                          setImportType(value)
                          setCityName('')
                          setCityConfirmed(false)
                          setError('')
                          setOverwritePrompt(null)
                        }}
                        className={`inline-flex items-center justify-center gap-2 rounded-xl border px-3 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${
                          importType === value
                            ? 'border-primary-600 bg-primary-50 text-primary-700'
                            : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <SearchableLocationInput
                  label="Country name"
                  value={countryName}
                  onChange={(value) => {
                    setCountryName(value)
                    setCountryIsoCode('')
                    if (!railImportNeedsSubdivision(value)) {
                      setCityName('')
                      setCityConfirmed(false)
                    }
                  }}
                  onSelect={(result) => {
                    const nextCountry = result.country || result.label || ''
                    setCountryName(nextCountry)
                    setCountryIsoCode((result.iso_code || '').toUpperCase())
                    if (!railImportNeedsSubdivision(nextCountry)) {
                      setCityName('')
                      setCityConfirmed(false)
                    }
                  }}
                  searchFn={searchCountries}
                  required
                  minChars={1}
                  placeholder="Search country"
                  disabled={submitting || !!activeTask}
                />
                {isAirportImport ? (
                  <div>
                    <label className="mb-1 block text-sm font-medium text-slate-700">Airport country ISO code *</label>
                    <input
                      value={countryIsoCode}
                      onChange={(event) => setCountryIsoCode(event.target.value.toUpperCase().slice(0, 2))}
                      required
                      maxLength={2}
                      placeholder="KH"
                      disabled={submitting || !!activeTask}
                      className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm uppercase text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:cursor-not-allowed disabled:bg-slate-50"
                    />
                  </div>
                ) : null}
                {!isAirportImport && requiresRailSubdivision ? (
                  <SearchableLocationInput
                    label={isChinaSelected ? 'City name' : 'City or region name'}
                    value={cityName}
                    onChange={(value) => {
                      setCityName(isChinaSelected ? normalizeChinaCityName(value) : value)
                      setCityConfirmed(false)
                    }}
                    onSelect={(result) => {
                      setCityName(isChinaSelected ? normalizeChinaCityName(result.city || result.label || '') : (result.city || result.label || ''))
                      setCityConfirmed(true)
                    }}
                    searchFn={(text) => searchCities(text, countryName)}
                    required
                    minChars={1}
                    placeholder={isChinaSelected ? 'Search China municipality or city' : `Search city or region in ${countryName}`}
                    disabled={submitting || !!activeTask}
                  />
                ) : null}
                <p className="text-xs text-slate-500">
                  {isAirportImport
                    ? <>Files will be saved in <code>geojson_file/&lt;country_name&gt;/&lt;country_name&gt;_airport_station.geojson</code>.</>
                    : <>Files will be saved in <code>geojson_file/&lt;country_name&gt;/</code> as <code>{requiresRailSubdivision ? '&lt;city_name&gt;' : '&lt;country_name&gt;'}.geojson</code> and <code>{requiresRailSubdivision ? '&lt;city_name&gt;' : '&lt;country_name&gt;'}_station.geojson</code>.</>}
                </p>
                {!isAirportImport && requiresRailSubdivision ? <p className="text-xs text-slate-500">
                  {isChinaSelected
                    ? 'For China imports, choose China first, then pick a municipality or city-level boundary from the dropdown.'
                    : `For ${countryName || 'large-country'} rail imports, choose a smaller city or region from the dropdown instead of importing the whole country.`}
                </p> : null}
                {!isAirportImport && requiresRailSubdivision && cityName.trim() && !cityConfirmed ? (
                  <p className="text-xs text-amber-600">Pick a city or region from the dropdown before starting the import.</p>
                ) : null}
                {!isAirportImport ? (
                  <p className="text-xs text-amber-600">
                    Very large rail countries such as the USA, Russia, and India should be imported by smaller region or city datasets rather than one full-country file.
                  </p>
                ) : null}
                <p className="text-xs text-slate-500">
                  Timeout is long but not unlimited, so a stuck Overpass request will still fail cleanly instead of hanging forever.
                </p>
                {error ? <p className="text-sm text-rose-600">{error}</p> : null}
                <Button
                  type="submit"
                  disabled={!canStartImport}
                  loading={submitting}
                  className="w-full"
                >
                  {activeTask ? 'Task Already Running' : isAirportImport ? 'Start Airport Import' : 'Start Rail Import'}
                </Button>
              </form>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-800">
                <Database className="h-4 w-4 text-primary-600" />
                Current Status
              </div>
              {activeTask ? (
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-slate-800">{activeTask.city_name ? `${activeTask.country_name} / ${activeTask.city_name}` : activeTask.country_name}</p>
                    <StatusBadge status={activeTask.status} />
                  </div>
                  <p className="text-xs font-medium uppercase text-slate-400">{activeTask.import_type || 'rail'}</p>
                  <p className="text-sm text-slate-500">{activeTask.stage}</p>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-primary-600 transition-all"
                      style={{ width: `${activeTask.progress_percent || 0}%` }}
                    />
                  </div>
                  <p className="text-xs text-slate-500">{activeTask.progress_percent || 0}% complete</p>
                </div>
              ) : (
                <p className="text-sm text-slate-500">No import is running right now.</p>
              )}
            </div>
          </div>

          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 px-5 py-4">
              <h2 className="text-sm font-semibold text-slate-800">Task History</h2>
              <p className="mt-1 text-xs text-slate-500">Newest tasks appear first. Only one task can be queued or running at any time.</p>
            </div>
            <div className="divide-y divide-slate-100">
              {tasks.length === 0 ? (
                <div className="px-5 py-10 text-center text-sm text-slate-400">No GeoJSON import tasks yet.</div>
              ) : (
                tasks.map((task) => (
                  <div key={task.id} className="px-5 py-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-slate-800">{task.city_name ? `${task.country_name} / ${task.city_name}` : task.country_name}</p>
                        <p className="text-xs text-slate-500">{task.dataset_key} {'\u00b7'} {task.import_type || 'rail'}</p>
                      </div>
                      <StatusBadge status={task.status} />
                    </div>
                    <p className="mt-2 text-sm text-slate-600">{task.stage}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {[task.line_file, task.station_file].filter(Boolean).join(' \u00b7 ')}
                    </p>
                    <p className="mt-1 text-xs text-slate-400">
                      Created: {task.created_at || '-'} {task.finished_at ? `\u00b7 Finished: ${task.finished_at}` : ''}
                    </p>
                    {task.error ? <p className="mt-2 text-sm text-rose-600">{task.error}</p> : null}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </Layout>
  )
}
