import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Info, RefreshCcw, Search, Settings2, ShieldAlert } from 'lucide-react'

import Layout from '../../components/layout/Layout'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import { routesApi } from '../../api/routes'
import { useAuth } from '../../contexts/AuthContext'

const ADMIN_EMAIL = 'hafiz.shadowfiend@gmail.com'

const MODE_LABELS = {
  google_osm: 'Google + OSM',
  geojson_osm: 'Local GeoJSON + OSM',
  osm_only: 'OSM Only',
}

function CapabilityBadge({ enabled, label }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
      {label}: {enabled ? 'yes' : 'no'}
    </span>
  )
}

export default function CountryRoutePoliciesPage() {
  const { user } = useAuth()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState([])
  const [draftModes, setDraftModes] = useState({})
  const [savingKey, setSavingKey] = useState('')
  const [error, setError] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [continentFilter, setContinentFilter] = useState('All')

  const isAllowed = (user?.email || '').toLowerCase() === ADMIN_EMAIL

  const loadPolicies = async () => {
    const data = await routesApi.countryRoutePolicies()
    const nextItems = data.items || []
    setItems(nextItems)
    setDraftModes(
      Object.fromEntries(
        nextItems.map((item) => [item.country_key, item.selected_mode]),
      ),
    )
  }

  useEffect(() => {
    if (!isAllowed) {
      setLoading(false)
      return
    }

    let cancelled = false
    ;(async () => {
      try {
        const data = await routesApi.countryRoutePolicies()
        if (cancelled) return
        const nextItems = data.items || []
        setItems(nextItems)
        setDraftModes(
          Object.fromEntries(
            nextItems.map((item) => [item.country_key, item.selected_mode]),
          ),
        )
        setError('')
      } catch (err) {
        if (!cancelled) {
          setError(err?.response?.data?.detail || 'Failed to load country route policies.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => { cancelled = true }
  }, [isAllowed])

  const summary = useMemo(() => {
    let google = 0
    let geojson = 0
    let osm = 0
    for (const item of items) {
      const mode = draftModes[item.country_key] || item.selected_mode
      if (mode === 'google_osm') google += 1
      else if (mode === 'geojson_osm') geojson += 1
      else osm += 1
    }
    return { google, geojson, osm }
  }, [draftModes, items])

  const continents = useMemo(() => {
    const values = new Set(items.map((item) => item.continent).filter(Boolean))
    return ['All', ...Array.from(values).sort()]
  }, [items])

  const filteredItems = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase()
    return items.filter((item) => {
      if (continentFilter !== 'All' && item.continent !== continentFilter) {
        return false
      }
      if (!normalizedQuery) {
        return true
      }
      const haystacks = [
        item.country_name,
        item.country_key,
        item.continent,
        ...(item.available_city_datasets || []),
      ]
      return haystacks.some((value) => (value || '').toLowerCase().includes(normalizedQuery))
    })
  }, [continentFilter, items, searchQuery])

  const handleSave = async (countryKey) => {
    const trainMode = draftModes[countryKey]
    if (!trainMode) return

    setSavingKey(countryKey)
    try {
      await routesApi.updateCountryRoutePolicy(countryKey, { train_mode: trainMode })
      const data = await routesApi.countryRoutePolicies()
      const nextItems = data.items || []
      setItems(nextItems)
      setDraftModes(
        Object.fromEntries(
          nextItems.map((item) => [item.country_key, item.selected_mode]),
        ),
      )
      setError('')
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to save country route policy.')
    } finally {
      setSavingKey('')
    }
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
          <p className="mt-2 text-sm text-slate-500">This train routing policy tool is only available to the admin account.</p>
        </div>
      </Layout>
    )
  }

  return (
    <Layout>
      <div className="space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <Link to="/dashboard" className="mb-2 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-primary-600">
              <ArrowLeft className="h-4 w-4" /> Dashboard
            </Link>
            <h1 className="text-2xl font-bold text-slate-800">Train Route Policies</h1>
            <p className="text-sm text-slate-500">
              Choose whether same-country train routes should prefer Google, local GeoJSON, or pure OSM for each country.
            </p>
          </div>
          <button
            type="button"
            onClick={async () => {
              try {
                await loadPolicies()
                setError('')
              } catch (err) {
                setError(err?.response?.data?.detail || 'Failed to refresh country route policies.')
              }
            }}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
          >
            <RefreshCcw className="h-4 w-4" />
            Refresh
          </button>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs uppercase tracking-wide text-slate-400">Google + OSM</p>
            <p className="mt-1 text-2xl font-semibold text-slate-800">{summary.google}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs uppercase tracking-wide text-slate-400">Local GeoJSON + OSM</p>
            <p className="mt-1 text-2xl font-semibold text-slate-800">{summary.geojson}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs uppercase tracking-wide text-slate-400">OSM Only</p>
            <p className="mt-1 text-2xl font-semibold text-slate-800">{summary.osm}</p>
          </div>
        </div>

        {error ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        ) : null}

        <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-[minmax(0,1fr)_220px]">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search country or local city dataset"
              className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-9 pr-3 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
            />
          </label>
          <select
            value={continentFilter}
            onChange={(event) => setContinentFilter(event.target.value)}
            className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
          >
            {continents.map((continent) => (
              <option key={continent} value={continent}>{continent}</option>
            ))}
          </select>
        </div>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-5 py-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              <Settings2 className="h-4 w-4 text-primary-600" />
              Country Policies
            </div>
            <p className="mt-1 text-xs text-slate-500">All countries are listed here. China, India, Russia, and the United States use one shared policy across any available local city or region rail datasets.</p>
          </div>
          <div className="divide-y divide-slate-100">
            {filteredItems.map((item) => (
              <div key={item.country_key} className="grid gap-4 px-5 py-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_220px_120px] lg:items-center">
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-slate-800">{item.country_name}</p>
                    {item.available_city_datasets?.length > 0 ? (
                      <div className="group relative">
                        <span className="inline-flex cursor-help items-center text-slate-400 transition group-hover:text-primary-600">
                          <Info className="h-4 w-4" />
                        </span>
                        <div className="pointer-events-none absolute left-0 top-full z-20 mt-2 hidden w-64 rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-600 shadow-xl group-hover:block">
                          <p className="font-semibold text-slate-800">Available local city datasets</p>
                          <p className="mt-1 leading-5">{item.available_city_datasets.join(', ')}</p>
                        </div>
                      </div>
                    ) : null}
                  </div>
                  <p className="text-xs text-slate-500">{item.continent}</p>
                  <div className="flex flex-wrap gap-2">
                    <CapabilityBadge enabled={item.supports_google} label="Google" />
                    <CapabilityBadge enabled={item.supports_geojson} label="GeoJSON" />
                  </div>
                </div>
                <div className="text-xs text-slate-500">
                  Available modes: {item.available_modes.map((mode) => MODE_LABELS[mode] || mode).join(', ')}
                </div>
                <select
                  value={draftModes[item.country_key] || item.selected_mode}
                  onChange={(event) => setDraftModes((current) => ({ ...current, [item.country_key]: event.target.value }))}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
                >
                  {item.available_modes.map((mode) => (
                    <option key={mode} value={mode}>{MODE_LABELS[mode] || mode}</option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => handleSave(item.country_key)}
                  disabled={savingKey === item.country_key || (draftModes[item.country_key] || item.selected_mode) === item.selected_mode}
                  className="inline-flex items-center justify-center rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-primary-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  {savingKey === item.country_key ? 'Saving...' : 'Save'}
                </button>
              </div>
            ))}
            {filteredItems.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-slate-500">
                No countries matched your search or continent filter.
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </Layout>
  )
}
