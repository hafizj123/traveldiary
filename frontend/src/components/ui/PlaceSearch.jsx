import { useState, useRef, useEffect } from 'react'
import { Search, MapPin } from 'lucide-react'
import { searchPlaceResults } from './locationSearch'

const METHOD_FILTERS = {
  train: {
    hint: 'train stations',
    nominatimQuery: (text) => `[railway=station] ${text}`,
    geoapifyType: 'amenity',
  },
  flight: {
    hint: 'airports',
    nominatimQuery: (text) => `[aeroway=aerodrome] ${text}`,
    geoapifyType: 'amenity',
  },
  ferry: {
    hint: 'ferry terminals',
    nominatimQuery: (text) => `[amenity=ferry_terminal] ${text}`,
    geoapifyType: 'amenity',
  },
  bus: {
    hint: 'bus stops',
    nominatimQuery: (text) => `[highway=bus_stop] ${text}`,
    geoapifyType: 'amenity',
  },
}

async function searchPlaces(text, travelMethod) {
  const filter = METHOD_FILTERS[travelMethod]
  return searchPlaceResults(text, {
    type: filter?.geoapifyType,
    nominatimQuery: filter ? filter.nominatimQuery(text) : undefined,
  })
}

export default function PlaceSearch({ onSelect, placeholder, label = 'Search place', travelMethod }) {
  const filter = METHOD_FILTERS[travelMethod]
  const defaultPlaceholder = filter
    ? `Search ${filter.hint} in English`
    : (placeholder || 'Search for a place in English')

  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const debounceRef = useRef(null)
  const containerRef = useRef(null)

  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => {
    setResults([])
    setOpen(false)
    setQuery('')
  }, [travelMethod])

  const handleChange = (text) => {
    setQuery(text)
    clearTimeout(debounceRef.current)
    if (text.trim().length < 3) {
      setResults([])
      setOpen(false)
      return
    }

    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const nextResults = await searchPlaces(text, travelMethod)
        setResults(nextResults)
        setOpen(nextResults.length > 0)
      } catch {
        setResults([])
        setOpen(false)
      } finally {
        setLoading(false)
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
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
        <input
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={defaultPlaceholder}
          className="w-full pl-9 pr-9 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
        {loading && (
          <span
            aria-hidden="true"
            className="absolute right-3 top-1/2 -translate-y-1/2 block h-4 w-4 rounded-full border-2 border-slate-200 border-t-primary-500 animate-spin"
          />
        )}
      </div>

      {open && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 z-50 mt-1 bg-white border border-slate-200 rounded-xl shadow-xl max-h-64 overflow-y-auto">
          {results.map((result) => (
            <button
              key={result.id}
              type="button"
              onClick={() => handleSelect(result)}
              className="w-full flex items-start gap-3 px-4 py-3 hover:bg-primary-50 text-left border-b border-slate-50 last:border-0 transition-colors"
            >
              <MapPin className="w-4 h-4 text-primary-400 flex-shrink-0 mt-0.5" />
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-700 truncate">{result.place_name}</p>
                <p className="text-xs text-slate-400 truncate">{result.subtitle}</p>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
