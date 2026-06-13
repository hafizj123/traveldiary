import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft,
  BadgeAlert,
  X,
  Database,
  Download,
  FileSearch,
  History,
  Info,
  Link2,
  RefreshCcw,
  Settings2,
  ShieldAlert,
  Stethoscope,
  UserCog,
  Wrench,
} from 'lucide-react'
import toast from 'react-hot-toast'

import Layout from '../../components/layout/Layout'
import Button from '../../components/ui/Button'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import AdminDataTable from '../../components/ui/AdminDataTable'
import { routesApi } from '../../api/routes'
import { useAuth } from '../../contexts/AuthContext'

const ADMIN_EMAIL = 'hafiz.shadowfiend@gmail.com'

const MODE_LABELS = {
  google_osm: 'Google + OSM',
  geojson_osm: 'Local GeoJSON + OSM',
  osm_only: 'OSM Only',
}

const ALIAS_METHOD_OPTIONS = [
  { value: '', label: 'Any method' },
  { value: 'train', label: 'Train' },
  { value: 'flight', label: 'Flight' },
  { value: 'ferry', label: 'Ferry' },
  { value: 'excursion', label: 'Excursion' },
  { value: 'bus', label: 'Bus' },
  { value: 'car', label: 'Car' },
  { value: 'walk', label: 'Walk' },
  { value: 'other', label: 'Other' },
]

const SPECIAL_CASE_EXAMPLES = [
  {
    label: 'Lauterbrunnen Lift Example',
    alias: 'Lauterbrunnen Lift',
    method: 'excursion',
    place_name: 'Lauterbrunnen',
    city: 'Lauterbrunnen',
    country: 'Switzerland',
    latitude: '46.5983618',
    longitude: '7.9080357',
    notes: 'Special lift alias for Lauterbrunnen station area.',
  },
  {
    label: 'Grutschalp Example',
    alias: 'Grutschalp',
    method: 'excursion',
    place_name: 'Gr\u00fctschalp',
    city: 'Lauterbrunnen',
    country: 'Switzerland',
    latitude: '46.5965617',
    longitude: '7.890707',
    notes: 'Alternative spelling that should resolve to Gr\u00fctschalp.',
  },
]

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function downloadJson(filename, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function StatCard({ label, value, hint }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-800">{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  )
}

function SectionCard({ title, subtitle, Icon, actions = null, children }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
            <Icon className="h-4 w-4 text-primary-600" />
            {title}
          </div>
          {subtitle ? <p className="mt-1 text-xs text-slate-500">{subtitle}</p> : null}
        </div>
        {actions}
      </div>
      <div className="px-5 py-4">{children}</div>
    </section>
  )
}

function ModePill({ mode }) {
  return (
    <span className="inline-flex rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700">
      {MODE_LABELS[mode] || mode || '-'}
    </span>
  )
}

export default function AdminToolsPage() {
  const { user } = useAuth()
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [systemStatus, setSystemStatus] = useState(null)
  const [dataHealth, setDataHealth] = useState(null)
  const [policies, setPolicies] = useState([])
  const [importHistory, setImportHistory] = useState([])
  const [brokenRoutes, setBrokenRoutes] = useState([])
  const [aliases, setAliases] = useState([])
  const [auditLogs, setAuditLogs] = useState([])
  const [trips, setTrips] = useState([])
  const [tripQuery, setTripQuery] = useState('')
  const [selectedTripId, setSelectedTripId] = useState(null)
  const [tripDetail, setTripDetail] = useState(null)
  const [tripDetailLoading, setTripDetailLoading] = useState(false)
  const [selectedCountryKeys, setSelectedCountryKeys] = useState([])
  const [bulkMode, setBulkMode] = useState('osm_only')
  const [bulkSaving, setBulkSaving] = useState(false)
  const [selectedBrokenRouteIds, setSelectedBrokenRouteIds] = useState([])
  const [cleanupLoading, setCleanupLoading] = useState(false)
  const [aliasSubmitting, setAliasSubmitting] = useState(false)
  const [aliasDeletingId, setAliasDeletingId] = useState(0)
  const [exportLoading, setExportLoading] = useState(false)
  const [normalizingTripId, setNormalizingTripId] = useState(0)
  const [aliasForm, setAliasForm] = useState({
    alias: '',
    method: '',
    place_name: '',
    city: '',
    country: '',
    latitude: '',
    longitude: '',
    notes: '',
  })

  const isAllowed = (user?.email || '').toLowerCase() === ADMIN_EMAIL

  const loadDashboard = async () => {
    const [
      systemData,
      healthData,
      importData,
      brokenData,
      aliasData,
      auditData,
      tripData,
      policyData,
    ] = await Promise.all([
      routesApi.adminSystemStatus(),
      routesApi.adminDataHealth(),
      routesApi.geojsonImportTasks(),
      routesApi.adminBrokenRoutes({ limit: 120 }),
      routesApi.adminSearchAliases(),
      routesApi.adminAuditLogs({ limit: 120 }),
      routesApi.adminTrips({ query: '', limit: 60 }),
      routesApi.countryRoutePolicies(),
    ])

    setSystemStatus(systemData)
    setDataHealth(healthData)
    setImportHistory(importData.items || [])
    setBrokenRoutes(brokenData.items || [])
    setAliases(aliasData.items || [])
    setAuditLogs(auditData.items || [])
    setTrips(tripData.items || [])
    setPolicies(policyData.items || [])
  }

  const loadTrips = async (query) => {
    const data = await routesApi.adminTrips({ query, limit: 60 })
    setTrips(data.items || [])
  }

  const loadTripDetail = async (tripId) => {
    if (!tripId) {
      setTripDetail(null)
      return
    }
    setTripDetailLoading(true)
    try {
      const data = await routesApi.adminTripDetail(tripId)
      setTripDetail(data)
    } finally {
      setTripDetailLoading(false)
    }
  }

  useEffect(() => {
    if (!isAllowed) {
      setLoading(false)
      return
    }

    let cancelled = false
    ;(async () => {
      try {
        await loadDashboard()
        if (!cancelled) setError('')
      } catch (err) {
        if (!cancelled) {
          setError(err?.response?.data?.detail || 'Failed to load admin tools.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => { cancelled = true }
  }, [isAllowed])

  useEffect(() => {
    if (!selectedTripId) {
      setTripDetail(null)
      return
    }

    let cancelled = false
    setTripDetailLoading(true)
    ;(async () => {
      try {
        const data = await routesApi.adminTripDetail(selectedTripId)
        if (!cancelled) {
          setTripDetail(data)
          setError('')
        }
      } catch (err) {
        if (!cancelled) {
          setError(err?.response?.data?.detail || 'Failed to load trip detail.')
        }
      } finally {
        if (!cancelled) setTripDetailLoading(false)
      }
    })()

    return () => { cancelled = true }
  }, [selectedTripId])

  const selectedCountries = useMemo(
    () => policies.filter((item) => selectedCountryKeys.includes(item.country_key)),
    [policies, selectedCountryKeys],
  )

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await loadDashboard()
      if (selectedTripId) {
        await loadTripDetail(selectedTripId)
      }
      setError('')
      setNotice('')
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to refresh admin tools.')
    } finally {
      setRefreshing(false)
    }
  }

  const handleBulkToggle = (countryKey) => {
    setError('')
    setSelectedCountryKeys((current) => (
      current.includes(countryKey)
        ? current.filter((item) => item !== countryKey)
        : [...current, countryKey]
    ))
  }

  const handleBulkApply = async () => {
    if (!selectedCountryKeys.length) return
    setError('')
    setBulkSaving(true)
    try {
      const data = await routesApi.adminBulkUpdateCountryRoutePolicies({
        country_keys: selectedCountryKeys,
        train_mode: bulkMode,
      })
      setPolicies(data.capabilities || [])
      setSelectedCountryKeys([])
      setError('')
      const updatedCount = (data.items || []).length
      const failedItems = data.failed || []
      if (failedItems.length > 0) {
        const failedNames = failedItems.map((item) => item.country_name || item.country_key).join(', ')
        const message = `Updated ${updatedCount} country policy${updatedCount === 1 ? '' : 'ies'}. Skipped ${failedItems.length}: ${failedNames}.`
        setNotice(message)
        toast(message)
      } else {
        const message = `Updated ${updatedCount} country policy${updatedCount === 1 ? '' : 'ies'} successfully.`
        setNotice(message)
        toast.success(message)
      }
    } catch (err) {
      const message = err?.response?.data?.detail || 'Failed to update route policies.'
      setError(message)
      setNotice('')
      toast.error(message)
    } finally {
      setBulkSaving(false)
    }
  }

  const handleBrokenRouteToggle = (routeId) => {
    setSelectedBrokenRouteIds((current) => (
      current.includes(routeId)
        ? current.filter((item) => item !== routeId)
        : [...current, routeId]
    ))
  }

  const handleBrokenRouteDelete = async () => {
    if (!selectedBrokenRouteIds.length) return
    setCleanupLoading(true)
    try {
      await routesApi.adminDeleteRouteCache({
        ids: selectedBrokenRouteIds,
        country: null,
        provider: null,
      })
      const [brokenData, systemData, healthData] = await Promise.all([
        routesApi.adminBrokenRoutes({ limit: 120 }),
        routesApi.adminSystemStatus(),
        routesApi.adminDataHealth(),
      ])
      setBrokenRoutes(brokenData.items || [])
      setSystemStatus(systemData)
      setDataHealth(healthData)
      setSelectedBrokenRouteIds([])
      setError('')
      setNotice(`Deleted ${selectedBrokenRouteIds.length} broken route cache row${selectedBrokenRouteIds.length === 1 ? '' : 's'}.`)
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to delete route cache rows.')
    } finally {
      setCleanupLoading(false)
    }
  }

  const handleAliasSubmit = async (event) => {
    event.preventDefault()
    setAliasSubmitting(true)
    try {
      await routesApi.adminCreateSearchAlias({
        alias: aliasForm.alias.trim(),
        method: aliasForm.method || null,
        place_name: aliasForm.place_name.trim(),
        city: aliasForm.city.trim() || null,
        country: aliasForm.country.trim(),
        latitude: Number(aliasForm.latitude),
        longitude: Number(aliasForm.longitude),
        notes: aliasForm.notes.trim() || null,
        is_active: true,
      })
      const data = await routesApi.adminSearchAliases()
      setAliases(data.items || [])
      setAliasForm({
        alias: '',
        method: '',
        place_name: '',
        city: '',
        country: '',
        latitude: '',
        longitude: '',
        notes: '',
      })
      setError('')
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to create search alias.')
    } finally {
      setAliasSubmitting(false)
    }
  }

  const handleAliasDelete = async (aliasId) => {
    setAliasDeletingId(aliasId)
    try {
      await routesApi.adminDeleteSearchAlias(aliasId)
      setAliases((current) => current.filter((item) => item.id !== aliasId))
      setError('')
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to delete search alias.')
    } finally {
      setAliasDeletingId(0)
    }
  }

  const handleExport = async () => {
    setExportLoading(true)
    try {
      const data = await routesApi.adminExport({ include_route_cache: false })
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
      downloadJson(`travel-diary-admin-export-${stamp}.json`, data)
      setError('')
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to export admin snapshot.')
    } finally {
      setExportLoading(false)
    }
  }

  const handleTripSearch = async (event) => {
    event.preventDefault()
    try {
      await loadTrips(tripQuery)
      setError('')
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to search trips.')
    }
  }

  const handleNormalizeTrip = async (tripId) => {
    setNormalizingTripId(tripId)
    try {
      await routesApi.adminNormalizeTripSequence(tripId)
      await Promise.all([loadTrips(tripQuery), loadTripDetail(tripId)])
      setError('')
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to normalize trip sequence.')
    } finally {
      setNormalizingTripId(0)
    }
  }

  const fillAliasExample = (example) => {
    setAliasForm({
      alias: example.alias,
      method: example.method,
      place_name: example.place_name,
      city: example.city,
      country: example.country,
      latitude: example.latitude,
      longitude: example.longitude,
      notes: example.notes,
    })
  }

  const countryHealthColumns = [
    {
      key: 'country_name',
      label: 'Country',
      render: (row) => (
        <div>
          <p className="font-semibold text-slate-800">{row.country_name}</p>
          <p className="text-xs text-slate-500">{row.country_key}</p>
        </div>
      ),
      searchValue: (row) => [row.country_name, row.country_key].join(' '),
    },
    { key: 'continent', label: 'Continent' },
    {
      key: 'selected_mode',
      label: 'Route Mode',
      render: (row) => <ModePill mode={row.selected_mode} />,
      searchValue: (row) => MODE_LABELS[row.selected_mode] || row.selected_mode,
    },
    { key: 'dataset_count', label: 'Datasets', className: 'text-right', headerClassName: 'text-right' },
    { key: 'route_cache_count', label: 'Cache Rows', className: 'text-right', headerClassName: 'text-right' },
    {
      key: 'last_import_at',
      label: 'Last Import',
      render: (row) => formatDateTime(row.last_import_at),
      sortValue: (row) => new Date(row.last_import_at || 0).getTime(),
    },
  ]

  const importHistoryColumns = [
    {
      key: 'country_name',
      label: 'Task',
      render: (row) => (
        <div>
          <p className="font-semibold text-slate-800">
            {row.city_name ? `${row.country_name} / ${row.city_name}` : row.country_name}
          </p>
          <p className="text-xs text-slate-500">{row.dataset_key || '-'}</p>
        </div>
      ),
      searchValue: (row) => [row.country_name, row.city_name, row.dataset_key].filter(Boolean).join(' '),
    },
    { key: 'status', label: 'Status' },
    { key: 'import_type', label: 'Import Mode' },
    {
      key: 'stage',
      label: 'Stage',
      render: (row) => row.stage || '-',
      sortable: false,
    },
    {
      key: 'created_at',
      label: 'Created',
      render: (row) => formatDateTime(row.created_at),
      sortValue: (row) => new Date(row.created_at || 0).getTime(),
    },
    {
      key: 'finished_at',
      label: 'Finished',
      render: (row) => formatDateTime(row.finished_at),
      sortValue: (row) => new Date(row.finished_at || 0).getTime(),
    },
  ]

  const brokenRouteColumns = [
    {
      key: 'select',
      label: 'Pick',
      sortable: false,
      render: (row) => (
        <input
          type="checkbox"
          checked={selectedBrokenRouteIds.includes(row.id)}
          onChange={() => handleBrokenRouteToggle(row.id)}
        />
      ),
    },
    {
      key: 'cache_key',
      label: 'Cache Key',
      render: (row) => <span className="font-mono text-xs text-slate-700">{row.cache_key}</span>,
    },
    { key: 'provider', label: 'Provider' },
    {
      key: 'countries',
      label: 'Countries',
      render: (row) => (row.countries || []).join(', ') || '-',
      searchValue: (row) => (row.countries || []).join(' '),
    },
    { key: 'point_count', label: 'Points', className: 'text-right', headerClassName: 'text-right' },
    {
      key: 'created_at',
      label: 'Created',
      render: (row) => formatDateTime(row.created_at),
      sortValue: (row) => new Date(row.created_at || 0).getTime(),
    },
  ]

  const policyColumns = [
    {
      key: 'select',
      label: 'Pick',
      sortable: false,
      render: (row) => (
        <input
          type="checkbox"
          checked={selectedCountryKeys.includes(row.country_key)}
          onChange={() => handleBulkToggle(row.country_key)}
        />
      ),
    },
    {
      key: 'country_name',
      label: 'Country',
      render: (row) => (
        <div>
          <p className="font-semibold text-slate-800">{row.country_name}</p>
          <p className="text-xs text-slate-500">{row.country_key}</p>
        </div>
      ),
      searchValue: (row) => [row.country_name, row.country_key, row.continent, ...(row.available_city_datasets || [])].filter(Boolean).join(' '),
    },
    { key: 'continent', label: 'Continent' },
    {
      key: 'selected_mode',
      label: 'Current Mode',
      render: (row) => <ModePill mode={row.selected_mode} />,
      searchValue: (row) => MODE_LABELS[row.selected_mode] || row.selected_mode,
    },
    {
      key: 'available_modes',
      label: 'Available Modes',
      render: (row) => row.available_modes.map((mode) => MODE_LABELS[mode] || mode).join(', '),
      sortable: false,
      searchValue: (row) => row.available_modes.join(' '),
    },
    {
      key: 'available_city_datasets',
      label: 'Local City Datasets',
      render: (row) => row.available_city_datasets?.join(', ') || '-',
      sortable: false,
      searchValue: (row) => (row.available_city_datasets || []).join(' '),
    },
  ]

  const aliasColumns = [
    { key: 'alias', label: 'Alias' },
    { key: 'method', label: 'Method', render: (row) => row.method || 'any' },
    {
      key: 'place_name',
      label: 'Resolved Place',
      render: (row) => (
        <div>
          <p className="font-semibold text-slate-800">{row.place_name}</p>
          <p className="text-xs text-slate-500">{[row.city, row.country].filter(Boolean).join(', ')}</p>
        </div>
      ),
      searchValue: (row) => [row.alias, row.place_name, row.city, row.country, row.notes].filter(Boolean).join(' '),
    },
    {
      key: 'latitude',
      label: 'Coordinates',
      render: (row) => `${Number(row.latitude).toFixed(5)}, ${Number(row.longitude).toFixed(5)}`,
      sortValue: (row) => Number(row.latitude),
    },
    { key: 'notes', label: 'Notes', render: (row) => row.notes || '-' },
    {
      key: 'actions',
      label: 'Action',
      sortable: false,
      render: (row) => (
        <Button
          size="sm"
          variant="danger"
          onClick={() => handleAliasDelete(row.id)}
          loading={aliasDeletingId === row.id}
        >
          Delete
        </Button>
      ),
    },
  ]

  const auditColumns = [
    {
      key: 'created_at',
      label: 'Time',
      render: (row) => formatDateTime(row.created_at),
      sortValue: (row) => new Date(row.created_at || 0).getTime(),
    },
    { key: 'action', label: 'Action' },
    { key: 'actor_email', label: 'Actor', render: (row) => row.actor_email || 'unknown user' },
    {
      key: 'resource_type',
      label: 'Resource',
      render: (row) => `${row.resource_type}${row.resource_id ? ` #${row.resource_id}` : ''}`,
      searchValue: (row) => [row.resource_type, row.resource_id, row.action, row.actor_email].filter(Boolean).join(' '),
    },
  ]

  const tripColumns = [
    { key: 'title', label: 'Trip' },
    { key: 'owner_email', label: 'Owner', render: (row) => row.owner_email || row.owner_username || '-' },
    { key: 'starting_country', label: 'Country', render: (row) => row.starting_country || '-' },
    { key: 'point_count', label: 'Points', className: 'text-right', headerClassName: 'text-right' },
    {
      key: 'updated_at',
      label: 'Updated',
      render: (row) => formatDateTime(row.updated_at),
      sortValue: (row) => new Date(row.updated_at || 0).getTime(),
    },
    {
      key: 'actions',
      label: 'Action',
      sortable: false,
      render: (row) => (
        <Button size="sm" variant="secondary" onClick={() => setSelectedTripId(row.trip_id)}>
          Inspect
        </Button>
      ),
    },
  ]

  const pointColumns = [
    { key: 'sequence_no', label: 'Seq', className: 'text-right', headerClassName: 'text-right' },
    { key: 'place_name', label: 'Place' },
    {
      key: 'location',
      label: 'Location',
      sortable: false,
      render: (row) => [row.city, row.country].filter(Boolean).join(', ') || '-',
      searchValue: (row) => [row.city, row.country].filter(Boolean).join(' '),
    },
    {
      key: 'visit_date',
      label: 'Visit Date',
      render: (row) => row.visit_date || '-',
    },
  ]

  const segmentColumns = [
    { key: 'travel_method', label: 'Method' },
    { key: 'from_point_id', label: 'From', className: 'text-right', headerClassName: 'text-right' },
    { key: 'to_point_id', label: 'To', className: 'text-right', headerClassName: 'text-right' },
  ]

  if (loading) {
    return <Layout><div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div></Layout>
  }

  if (!isAllowed) {
    return (
      <Layout>
        <div className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <ShieldAlert className="mx-auto mb-4 h-10 w-10 text-slate-300" />
          <h1 className="text-xl font-semibold text-slate-800">Access Restricted</h1>
          <p className="mt-2 text-sm text-slate-500">This admin tools workspace is only available to the admin account.</p>
        </div>
      </Layout>
    )
  }

  return (
    <Layout>
      <div className="space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link to="/dashboard" className="mb-2 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-primary-600">
              <ArrowLeft className="h-4 w-4" /> Dashboard
            </Link>
            <h1 className="text-2xl font-bold text-slate-800">Admin Tools</h1>
            <p className="text-sm text-slate-500">
              One place to monitor route data, clean cache, repair trips, manage imports, and handle search overrides.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={handleRefresh} loading={refreshing}>
              <RefreshCcw className="h-4 w-4" />
              Refresh
            </Button>
            <Button onClick={handleExport} loading={exportLoading}>
              <Download className="h-4 w-4" />
              Export Snapshot
            </Button>
          </div>
        </div>

        {error ? (
          <div className="flex items-start justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            <span>{error}</span>
            <button
              type="button"
              onClick={() => setError('')}
              className="inline-flex h-6 w-6 items-center justify-center rounded-md text-rose-500 transition hover:bg-rose-100 hover:text-rose-700"
              aria-label="Dismiss error"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : null}

        {notice ? (
          <div className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
            {notice}
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          <StatCard label="Trips" value={systemStatus?.trip_count || 0} hint={`${systemStatus?.point_count || 0} points`} />
          <StatCard label="Route Cache" value={systemStatus?.route_cache_count || 0} hint={`${systemStatus?.segment_count || 0} segments`} />
          <StatCard label="Datasets" value={dataHealth?.summary?.dataset_count || 0} hint={`${dataHealth?.summary?.countries_with_local_data || 0} countries with local data`} />
          <StatCard label="Aliases" value={systemStatus?.search_alias_count || 0} hint={`${aliases.length} loaded`} />
          <StatCard label="Disk Free" value={`${systemStatus?.disk_free_mb || 0} MB`} hint={`${systemStatus?.backup_size_mb || 0} MB backups`} />
        </div>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
          <div className="space-y-5">
            <SectionCard
              title="System Status"
              subtitle="Quick backend and data storage health."
              Icon={Stethoscope}
              actions={(
                <div className="flex flex-wrap gap-2">
                  <Link to="/saved-routes" className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-50">Saved Routes</Link>
                  <Link to="/country-route-policies" className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-50">Policies</Link>
                  <Link to="/geojson-imports" className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-50">GeoJSON Imports</Link>
                </div>
              )}
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs uppercase tracking-wide text-slate-400">Database</p>
                  <p className="mt-1 break-all text-sm text-slate-700">{systemStatus?.database_path || '-'}</p>
                  <p className="mt-2 text-xs text-slate-500">Size: {systemStatus?.database_size_mb || 0} MB</p>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs uppercase tracking-wide text-slate-400">Dataset Root</p>
                  <p className="mt-1 break-all text-sm text-slate-700">{systemStatus?.dataset_root || '-'}</p>
                  <p className="mt-2 text-xs text-slate-500">
                    Active imports: {systemStatus?.active_import_tasks || 0} {'\u00b7'} Dataset size: {systemStatus?.dataset_size_mb || 0} MB
                  </p>
                </div>
              </div>
            </SectionCard>

            <SectionCard
              title="Data Health"
              subtitle="Sortable table for country coverage, local dataset counts, and route-cache footprint."
              Icon={Database}
            >
              <AdminDataTable
                title="Country Health"
                columns={countryHealthColumns}
                rows={dataHealth?.countries || []}
                rowKey="country_key"
                searchPlaceholder="Search country, continent, or route mode"
                initialSortKey="dataset_count"
                initialSortDirection="desc"
                emptyMessage="No country health data is available yet."
              />
            </SectionCard>

            <SectionCard
              title="Task History"
              subtitle="This table now uses the same single task-history source as the GeoJSON Import page."
              Icon={History}
            >
              <AdminDataTable
                title="Import Tasks"
                columns={importHistoryColumns}
                rows={importHistory}
                rowKey="id"
                searchPlaceholder="Search country, city, dataset key, stage, or status"
                initialSortKey="created_at"
                initialSortDirection="desc"
                emptyMessage="No import tasks are available yet."
              />
            </SectionCard>

            <SectionCard
              title="Broken Route Cache"
              subtitle="Pick multiple broken cache rows and delete only the ones you selected."
              Icon={BadgeAlert}
              actions={(
                <Button
                  size="sm"
                  variant="danger"
                  onClick={handleBrokenRouteDelete}
                  loading={cleanupLoading}
                  disabled={!selectedBrokenRouteIds.length}
                >
                  Delete Selected {selectedBrokenRouteIds.length || 0}
                </Button>
              )}
            >
              {selectedBrokenRouteIds.length > 0 ? (
                <p className="mb-4 text-xs text-slate-500">
                  Selected route ids: {selectedBrokenRouteIds.join(', ')}
                </p>
              ) : null}
              <AdminDataTable
                title="Broken Routes"
                columns={brokenRouteColumns}
                rows={brokenRoutes}
                rowKey="id"
                searchPlaceholder="Search cache key, provider, or country"
                initialSortKey="created_at"
                initialSortDirection="desc"
                emptyMessage="No broken route cache rows were found."
              />
            </SectionCard>
          </div>

          <div className="space-y-5">
            <SectionCard
              title="Bulk Route Policy"
              subtitle="Use the table like a data-table grid: search, sort, pick countries, then apply one train mode."
              Icon={Settings2}
              actions={(
                <Button size="sm" onClick={handleBulkApply} loading={bulkSaving} disabled={!selectedCountryKeys.length}>
                  Apply To {selectedCountryKeys.length || 0}
                </Button>
              )}
            >
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <select
                  value={bulkMode}
                  onChange={(event) => {
                    setBulkMode(event.target.value)
                    setError('')
                  }}
                  className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
                >
                  {Object.entries(MODE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
                {selectedCountries.length > 0 ? (
                  <p className="text-xs text-slate-500">
                    Selected: {selectedCountries.map((item) => item.country_name).join(', ')}
                  </p>
                ) : null}
              </div>
              <AdminDataTable
                title="Policy Countries"
                columns={policyColumns}
                rows={policies}
                rowKey="country_key"
                searchPlaceholder="Search country, continent, city dataset, or mode"
                initialSortKey="country_name"
                initialSortDirection="asc"
                emptyMessage="No route policy rows are available yet."
              />
            </SectionCard>

            <SectionCard
              title="Search Alias Overrides"
              subtitle="For a special case, add one alias row per search spelling and point all of them to the same real coordinates."
              Icon={Link2}
            >
              <div className="mb-4 rounded-2xl border border-sky-200 bg-sky-50 p-4">
                <div className="flex items-start gap-2">
                  <Info className="mt-0.5 h-4 w-4 text-sky-700" />
                  <div className="space-y-2 text-sm text-sky-900">
                    <p>
                      Example workflow: if users search <strong>Grutschalp</strong>, <strong>Gruetschalp</strong>, and <strong>Gr\u00fctschalp</strong>, create one row for each alias but keep the same resolved place and coordinates.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {SPECIAL_CASE_EXAMPLES.map((example) => (
                        <button
                          key={example.label}
                          type="button"
                          onClick={() => fillAliasExample(example)}
                          className="rounded-lg border border-sky-300 bg-white px-3 py-1.5 text-xs font-semibold text-sky-700 transition hover:bg-sky-100"
                        >
                          Use {example.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <form onSubmit={handleAliasSubmit} className="grid gap-3 md:grid-cols-2">
                <input
                  value={aliasForm.alias}
                  onChange={(event) => setAliasForm((current) => ({ ...current, alias: event.target.value }))}
                  placeholder="Alias text, for example Grutschalp"
                  required
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
                />
                <select
                  value={aliasForm.method}
                  onChange={(event) => setAliasForm((current) => ({ ...current, method: event.target.value }))}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
                >
                  {ALIAS_METHOD_OPTIONS.map((option) => (
                    <option key={option.label} value={option.value}>{option.label}</option>
                  ))}
                </select>
                <input
                  value={aliasForm.place_name}
                  onChange={(event) => setAliasForm((current) => ({ ...current, place_name: event.target.value }))}
                  placeholder="Resolved place name, for example Grütschalp"
                  required
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
                />
                <input
                  value={aliasForm.city}
                  onChange={(event) => setAliasForm((current) => ({ ...current, city: event.target.value }))}
                  placeholder="City"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
                />
                <input
                  value={aliasForm.country}
                  onChange={(event) => setAliasForm((current) => ({ ...current, country: event.target.value }))}
                  placeholder="Country"
                  required
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
                />
                <input
                  value={aliasForm.notes}
                  onChange={(event) => setAliasForm((current) => ({ ...current, notes: event.target.value }))}
                  placeholder="Notes, for example special lift alias"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
                />
                <input
                  type="number"
                  step="any"
                  value={aliasForm.latitude}
                  onChange={(event) => setAliasForm((current) => ({ ...current, latitude: event.target.value }))}
                  placeholder="Latitude"
                  required
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
                />
                <input
                  type="number"
                  step="any"
                  value={aliasForm.longitude}
                  onChange={(event) => setAliasForm((current) => ({ ...current, longitude: event.target.value }))}
                  placeholder="Longitude"
                  required
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
                />
                <div className="md:col-span-2">
                  <Button type="submit" loading={aliasSubmitting}>Create Alias</Button>
                </div>
              </form>

              <div className="mt-5">
                <AdminDataTable
                  title="Alias Overrides"
                  columns={aliasColumns}
                  rows={aliases}
                  rowKey="id"
                  searchPlaceholder="Search alias, resolved place, country, or notes"
                  initialSortKey="alias"
                  initialSortDirection="asc"
                  emptyMessage="No alias overrides have been created yet."
                />
              </div>
            </SectionCard>

            <SectionCard
              title="Audit Log"
              subtitle="Newest admin and content change records in one sortable table."
              Icon={FileSearch}
            >
              <AdminDataTable
                title="Audit Logs"
                columns={auditColumns}
                rows={auditLogs}
                rowKey="id"
                searchPlaceholder="Search action, actor, resource, or id"
                initialSortKey="created_at"
                initialSortDirection="desc"
                emptyMessage="No audit records are available yet."
              />
            </SectionCard>
          </div>
        </div>

        <SectionCard
          title="Trip Repair"
          subtitle="Search trips, inspect timeline order, and normalize sequence numbers when old data got out of sync."
          Icon={Wrench}
        >
          <div className="space-y-5">
            <form onSubmit={handleTripSearch} className="flex flex-wrap gap-3">
              <input
                value={tripQuery}
                onChange={(event) => setTripQuery(event.target.value)}
                placeholder="Search trip title, owner, or country from the server"
                className="min-w-[280px] flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
              />
              <Button type="submit" variant="secondary">Search Trips</Button>
            </form>

            <AdminDataTable
              title="Trips"
              columns={tripColumns}
              rows={trips}
              rowKey="trip_id"
              searchPlaceholder="Filter loaded trips in the table"
              initialSortKey="updated_at"
              initialSortDirection="desc"
              emptyMessage="No trips matched your search."
            />

            <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
              {!selectedTripId ? (
                <div className="flex min-h-[14rem] items-center justify-center text-sm text-slate-500">
                  Pick a trip from the table to inspect its points and segments.
                </div>
              ) : tripDetailLoading ? (
                <div className="flex min-h-[14rem] items-center justify-center">
                  <LoadingSpinner size="lg" />
                </div>
              ) : !tripDetail ? (
                <div className="flex min-h-[14rem] items-center justify-center text-sm text-slate-500">
                  Trip detail could not be loaded.
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-lg font-semibold text-slate-800">{tripDetail.trip?.title}</p>
                      <p className="text-sm text-slate-500">
                        {tripDetail.trip?.owner_email || tripDetail.trip?.owner_username || '-'} {'\u00b7'} {tripDetail.points?.length || 0} points {'\u00b7'} {tripDetail.segments?.length || 0} segments
                      </p>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => handleNormalizeTrip(selectedTripId)}
                      loading={normalizingTripId === selectedTripId}
                    >
                      <UserCog className="h-4 w-4" />
                      Normalize Sequence
                    </Button>
                  </div>

                  <div className="grid gap-4 xl:grid-cols-2">
                    <AdminDataTable
                      title="Trip Points"
                      columns={pointColumns}
                      rows={tripDetail.points || []}
                      rowKey="id"
                      searchPlaceholder="Search place, city, country, or date"
                      initialSortKey="sequence_no"
                      initialSortDirection="asc"
                      emptyMessage="No points were found for this trip."
                      initialPageSize={6}
                    />
                    <AdminDataTable
                      title="Trip Segments"
                      columns={segmentColumns}
                      rows={tripDetail.segments || []}
                      rowKey="id"
                      searchPlaceholder="Search method or point ids"
                      initialSortKey="id"
                      initialSortDirection="asc"
                      emptyMessage="No segments were found for this trip."
                      initialPageSize={6}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </SectionCard>
      </div>
    </Layout>
  )
}
