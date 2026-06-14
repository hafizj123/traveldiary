import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Database, Globe, Route } from 'lucide-react'
import { MapContainer, TileLayer, Polyline, useMap } from 'react-leaflet'

import Layout from '../../components/layout/Layout'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import SearchableLocationInput from '../../components/ui/SearchableLocationInput'
import { routesApi } from '../../api/routes'
import { useAuth } from '../../contexts/AuthContext'
import { DEFAULT_MAP_PROPS, DEFAULT_TILE_PROPS } from '../../components/map/mapConfig'
const ROUTE_COLOR = '#0f766e'
const SUMMARY_LIMIT = 400
const MAP_ROUTE_LIMIT = 120

function FitToRoutes({ items }) {
  const map = useMap()

  useEffect(() => {
    const coords = items.flatMap((item) => item.geometry || [])
    const timeoutId = window.setTimeout(() => {
      map.invalidateSize()
      if (!coords.length) return
      map.fitBounds(coords.map(([lat, lon]) => [lat, lon]), { padding: [36, 36] })
    }, 0)

    return () => window.clearTimeout(timeoutId)
  }, [items, map])

  return null
}

export default function SavedRoutesPage() {
  const { user } = useAuth()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState([])
  const [mapItems, setMapItems] = useState([])
  const [mapLoading, setMapLoading] = useState(false)
  const [selectedCountry, setSelectedCountry] = useState('')
  const [countryQuery, setCountryQuery] = useState('')

  const isAllowed = Boolean(user?.is_admin)

  useEffect(() => {
    if (!isAllowed) {
      setLoading(false)
      return
    }

    let cancelled = false
    ;(async () => {
      try {
        const data = await routesApi.savedRouteCache({ limit: SUMMARY_LIMIT, include_geometry: false })
        if (cancelled) return

        const dedupedMap = new Map()
        for (const item of data.items || []) {
          const signature = item.geometry_signature || item.cache_key
          if (!dedupedMap.has(signature)) {
            dedupedMap.set(signature, item)
          }
        }

        setItems(Array.from(dedupedMap.values()))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => { cancelled = true }
  }, [isAllowed])

  const countries = useMemo(() => {
    const set = new Set()
    for (const item of items) {
      for (const country of item.countries || []) {
        if (country) set.add(country)
      }
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [items])

  useEffect(() => {
    if (!countries.length) {
      if (selectedCountry) {
        setSelectedCountry('')
        setCountryQuery('')
      }
      return
    }
    if (!selectedCountry || !countries.includes(selectedCountry)) {
      setSelectedCountry(countries[0])
      setCountryQuery(countries[0])
    }
  }, [countries, selectedCountry])

  const searchCountries = async (query) => {
    const normalizedQuery = query.trim().toLowerCase()
    if (normalizedQuery.length < 1) {
      return countries.slice(0, 20).map((country) => ({
        id: country,
        label: country,
      }))
    }

    return countries
      .filter((country) => country.toLowerCase().includes(normalizedQuery))
      .slice(0, 20)
      .map((country) => ({
        id: country,
        label: country,
      }))
  }

  const filteredItems = useMemo(() => {
    if (!selectedCountry) return []
    return items.filter((item) => (item.countries || []).includes(selectedCountry))
  }, [items, selectedCountry])

  const visibleItems = filteredItems
  const visibleMapCount = Math.min(visibleItems.length, MAP_ROUTE_LIMIT)

  useEffect(() => {
    if (!isAllowed || loading || !selectedCountry) {
      return
    }

    let cancelled = false
    ;(async () => {
      setMapLoading(true)
      try {
        const data = await routesApi.savedRouteCache({
          limit: MAP_ROUTE_LIMIT,
          include_geometry: true,
          country: selectedCountry,
        })
        if (cancelled) return

        const dedupedMap = new Map()
        for (const item of data.items || []) {
          const signature = item.geometry_signature || item.cache_key
          if (!dedupedMap.has(signature)) {
            dedupedMap.set(signature, item)
          }
        }
        setMapItems(Array.from(dedupedMap.values()))
      } finally {
        if (!cancelled) setMapLoading(false)
      }
    })()

    return () => { cancelled = true }
  }, [isAllowed, loading, selectedCountry])

  if (loading) {
    return <Layout><div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div></Layout>
  }

  if (!isAllowed) {
    return (
      <Layout>
        <div className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <Database className="mx-auto mb-4 h-10 w-10 text-slate-300" />
          <h1 className="text-xl font-semibold text-slate-800">Access Restricted</h1>
          <p className="mt-2 text-sm text-slate-500">This saved route viewer is only available to the admin account.</p>
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
            <h1 className="text-2xl font-bold text-slate-800">Saved Route Cache</h1>
            <p className="text-sm text-slate-500">Saved route geometries are loaded country by country for faster viewing.</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-right shadow-sm">
            <p className="text-xs uppercase tracking-wide text-slate-400">Unique Routes</p>
            <p className="text-2xl font-semibold text-slate-800">{items.length}</p>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
          <div className="space-y-5">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <label className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-800">
                <Globe className="h-4 w-4 text-primary-600" />
                Zoom To Country
              </label>
              <SearchableLocationInput
                value={countryQuery}
                onChange={setCountryQuery}
                onSelect={(result) => {
                  setSelectedCountry(result.label)
                  setCountryQuery(result.label)
                }}
                searchFn={searchCountries}
                placeholder="Search country"
                minChars={1}
                minLoadingMs={180}
              />
              <p className="mt-2 text-xs text-slate-500">
                Showing {visibleItems.length} route{visibleItems.length === 1 ? '' : 's'} in {selectedCountry || 'the selected country'}.
                {' '}The map loads up to {visibleMapCount} route{visibleMapCount === 1 ? '' : 's'} for performance.
              </p>
            </div>

            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-4 py-3">
                <p className="text-sm font-semibold text-slate-800">Visible Routes</p>
                <p className="text-xs text-slate-500">This list follows the current country filter.</p>
              </div>
              <div className="h-[48vh] overflow-y-auto overscroll-contain sm:h-[54vh] lg:h-[calc(100vh-18rem)]">
                {visibleItems.length === 0 ? (
                  <div className="px-4 py-10 text-center text-sm text-slate-400">No saved routes match this country.</div>
                ) : (
                  visibleItems.map((item) => (
                    <div key={item.id} className="border-b border-slate-100 px-4 py-3 last:border-b-0">
                      <p className="truncate text-sm font-semibold text-slate-800">{item.cache_key}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        Provider: {item.provider || 'unknown'} {'\u00b7'} Points: {item.point_count}
                      </p>
                      <p className="mt-1 text-xs text-slate-400">
                        {(item.countries || []).join(', ') || 'Country unknown'}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:flex lg:min-h-0 lg:h-full lg:flex-col">
            <div className="border-b border-slate-100 px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                <Route className="h-4 w-4 text-primary-600" />
                {selectedCountry ? `Saved Routes in ${selectedCountry}` : 'Saved Routes'}
              </div>
              <p className="mt-1 text-xs text-slate-500">Only the newest visible saved route geometries are drawn on the map to keep loading fast.</p>
            </div>

            <div className="h-[48vh] min-h-[320px] bg-slate-100 sm:h-[54vh] lg:min-h-[420px] lg:flex-1 lg:h-auto">
              {items.length === 0 ? (
                <div className="flex h-full items-center justify-center text-sm text-slate-400">No route cache rows to display.</div>
              ) : !selectedCountry ? (
                <div className="flex h-full items-center justify-center text-sm text-slate-400">No country is available yet.</div>
              ) : mapLoading ? (
                <div className="flex h-full items-center justify-center">
                  <LoadingSpinner size="lg" />
                </div>
              ) : (
                <MapContainer
                  center={[20, 0]}
                  zoom={2}
                  className="h-full w-full"
                  preferCanvas={true}
                  {...DEFAULT_MAP_PROPS}
                >
                  <TileLayer
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                    {...DEFAULT_TILE_PROPS}
                  />
                  <FitToRoutes items={mapItems} />
                  {mapItems.map((item) => (
                    <Polyline
                      key={item.id}
                      positions={item.geometry}
                      pathOptions={{
                        color: ROUTE_COLOR,
                        weight: 3,
                        opacity: 0.78,
                      }}
                    />
                  ))}
                </MapContainer>
              )}
            </div>
          </div>
        </div>
      </div>
    </Layout>
  )
}
