import { useEffect, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { searchPlaceResults } from './locationSearch'
import { getLocationResultIcon, getLocationResultKind } from './locationResultIcon'
import { routesApi } from '../../api/routes'
import LoadingSpinner from './LoadingSpinner'

const METHOD_FILTERS = {
  train: {
    hint: 'train stations',
    nominatimQuery: (text) => text,
    geoapifyType: 'amenity',
  },
  flight: {
    hint: 'airports',
    nominatimQuery: (text) => `${text} airport`,
    geoapifyType: 'amenity',
    geoapifyCategories: 'airport',
  },
  ferry: {
    hint: 'ferry terminals',
    nominatimQuery: (text) => `${text} ferry terminal`,
    geoapifyType: 'amenity',
  },
  excursion: {
    hint: 'cable cars and gondolas in Europe',
    nominatimQuery: (text) => `${text} cable car`,
    geoapifyType: 'amenity',
  },
  bus: {
    hint: 'any destination in selected country',
    nominatimQuery: (text, country) => (country ? `${text}, ${country}` : text),
  },
}

const EXPECTED_KIND = {
  flight: 'airport',
  train: 'train',
  ferry: 'ferry',
  excursion: 'excursion',
}

const KIND_COLORS = {
  train: 'text-red-400',
  airport: 'text-blue-400',
  ferry: 'text-cyan-500',
  bus: 'text-orange-400',
  excursion: 'text-amber-500',
  location: 'text-primary-400',
}

const KIND_BADGE = {
  train: { label: 'Train', cls: 'bg-red-50 text-red-600' },
  airport: { label: 'Airport', cls: 'bg-blue-50 text-blue-600' },
  ferry: { label: 'Ferry', cls: 'bg-cyan-50 text-cyan-700' },
  bus: { label: 'Bus', cls: 'bg-orange-50 text-orange-600' },
  excursion: { label: 'Lift', cls: 'bg-amber-50 text-amber-700' },
}

async function searchPlaces(text, travelMethod, country, multiCountry) {
  const normalizedCountry = (country || '').trim() || undefined

  // Car/bus/walk/other methods require a country to be selected first so the
  // search is scoped to that country and does not return irrelevant global results.
  const COUNTRY_REQUIRED_METHODS = ['car', 'bus', 'walk', 'other']
  if (COUNTRY_REQUIRED_METHODS.includes(travelMethod) && !normalizedCountry) {
    return null
  }

  if (travelMethod === 'train') {
    const response = await routesApi.searchTrainStations({
      q: text,
      limit: 8,
      country: normalizedCountry,
      include_eu_international: multiCountry ? true : undefined,
    })
    const localResults = (response?.results || []).map((result) => ({
      ...result,
      transport_mode: 'train',
    }))
    if (response?.has_local_data || localResults.length > 0) {
      return localResults
    }
  }

  if (travelMethod === 'flight') {
    const response = await routesApi.searchTransportPlaces({
      q: text,
      method: 'flight',
      country: normalizedCountry,
      limit: 8,
    })
    return (response?.results || []).map((result) => ({
      ...result,
      transport_mode: 'flight',
    }))
  }

  if (travelMethod === 'ferry' || travelMethod === 'excursion') {
    const response = await routesApi.searchTransportPlaces({
      q: text,
      method: travelMethod,
      country: normalizedCountry,
      limit: 8,
    })
    return (response?.results || []).map((result) => ({
      ...result,
      transport_mode: travelMethod,
    }))
  }

  const filter = METHOD_FILTERS[travelMethod]
  const nominatimQuery = filter
    ? filter.nominatimQuery(text, normalizedCountry)
    : (normalizedCountry ? `${text}, ${normalizedCountry}` : text)

  const rawResults = await searchPlaceResults(text, {
    type: filter?.geoapifyType,
    categories: filter?.geoapifyCategories,
    nominatimQuery,
  })

  let results = rawResults
  if (normalizedCountry) {
    const countryLower = normalizedCountry.toLowerCase()
    results = results.filter(
      (result) => (result.country || '').toLowerCase() === countryLower,
    )
  }

  const expectedKind = EXPECTED_KIND[travelMethod]
  if (expectedKind) {
    const filtered = results.filter(
      (result) => getLocationResultKind(result) === expectedKind,
    )
    return filtered.length > 0 ? filtered : results
  }

  return results
}

export default function PlaceSearch({
  onSelect,
  placeholder,
  label = 'Search place',
  travelMethod,
  country = '',
  multiCountry = false,
}) {
  const filter = METHOD_FILTERS[travelMethod]
  const defaultPlaceholder = filter
    ? `Search ${filter.hint} in English`
    : (placeholder || 'Search for a place in English')

  const COUNTRY_REQUIRED_METHODS = ['car', 'bus', 'walk', 'other']
  const requiresCountry = COUNTRY_REQUIRED_METHODS.includes(travelMethod)
  const hasCountry = Boolean((country || '').trim())

  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const debounceRef = useRef(null)
  const containerRef = useRef(null)
  const requestIdRef = useRef(0)

  useEffect(() => {
    const handler = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => () => clearTimeout(debounceRef.current), [])

  useEffect(() => {
    setResults([])
    setOpen(false)
    setLoading(false)
    setQuery('')
  }, [travelMethod])

  useEffect(() => {
    clearTimeout(debounceRef.current)

    if (query.trim().length < 3) {
      setResults([])
      setOpen(false)
      setLoading(false)
      return
    }

    if (requiresCountry && !hasCountry) {
      setResults([])
      setOpen(false)
      setLoading(false)
      return
    }

    debounceRef.current = setTimeout(async () => {
      const requestId = ++requestIdRef.current
      setLoading(true)
      try {
        const nextResults = await searchPlaces(query, travelMethod, country, multiCountry)
        if (requestId !== requestIdRef.current) return
        if (nextResults === null) {
          setResults([])
          setOpen(false)
          return
        }
        setResults(nextResults)
        setOpen(nextResults.length > 0)
      } catch {
        if (requestId !== requestIdRef.current) return
        setResults([])
        setOpen(false)
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false)
        }
      }
    }, 150)
  }, [country])

  const handleChange = (text) => {
    setQuery(text)
    clearTimeout(debounceRef.current)

    if (text.trim().length < 3) {
      setResults([])
      setOpen(false)
      setLoading(false)
      return
    }

    if (requiresCountry && !hasCountry) {
      setResults([])
      setOpen(false)
      setLoading(false)
      return
    }

    debounceRef.current = setTimeout(async () => {
      const requestId = ++requestIdRef.current
      setLoading(true)
      try {
        const nextResults = await searchPlaces(text, travelMethod, country, multiCountry)
        if (requestId !== requestIdRef.current) return
        if (nextResults === null) {
          setResults([])
          setOpen(false)
          return
        }
        setResults(nextResults)
        setOpen(nextResults.length > 0)
      } catch {
        if (requestId !== requestIdRef.current) return
        setResults([])
        setOpen(false)
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false)
        }
      }
    }, 350)
  }

  const handleSelect = (result) => {
    onSelect({
      place_name: result.place_name,
      city: result.city,
      country: result.country,
      latitude: result.latitude,
      longitude: result.longitude,
    })
    setQuery('')
    setOpen(false)
    setResults([])
  }

  return (
    <div ref={containerRef} className="relative">
      {label && (
        <label className="block text-sm font-medium text-slate-700 mb-1">
          {label}
          {filter && (
            <span className="ml-2 text-xs font-normal text-primary-500">
              Filtered to {filter.hint}
            </span>
          )}
        </label>
      )}
      {requiresCountry && !hasCountry && (
        <p className="text-xs text-amber-600 mb-1">
          Please select a country above before searching.
        </p>
      )}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
        <input
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={defaultPlaceholder}
          className="w-full pl-9 pr-9 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
        {loading && (
          <div className="pointer-events-none absolute inset-y-0 right-3 flex items-center">
            <LoadingSpinner size="sm" className="block" />
          </div>
        )}
      </div>

      {open && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 z-50 mt-1 bg-white border border-slate-200 rounded-xl shadow-xl max-h-64 overflow-y-auto">
          {results.map((result) => {
            const kind = getLocationResultKind(result)
            const Icon = getLocationResultIcon(kind)
            const iconColor = KIND_COLORS[kind] || KIND_COLORS.location
            const badge = KIND_BADGE[kind]
            return (
              <button
                key={result.id}
                type="button"
                onClick={() => handleSelect(result)}
                className="w-full flex items-start gap-3 px-4 py-3 hover:bg-primary-50 text-left border-b border-slate-50 last:border-0 transition-colors"
              >
                <Icon className={`w-4 h-4 ${iconColor} flex-shrink-0 mt-0.5`} />
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <p className="text-sm font-medium text-slate-700 truncate">{result.place_name}</p>
                    {badge && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold flex-shrink-0 ${badge.cls}`}>
                        {badge.label}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 truncate">{result.subtitle}</p>
                </div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
