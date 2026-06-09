import { useState, useRef, useEffect } from 'react'
import { Search, MapPin, Loader2 } from 'lucide-react'

// Nominatim tag filters per travel method
const METHOD_FILTERS = {
  train:  { tag: 'railway=station',     hint: 'train stations',  icon: '🚉' },
  flight: { tag: 'aeroway=aerodrome',   hint: 'airports',        icon: '✈️' },
  ferry:  { tag: 'amenity=ferry_terminal', hint: 'ferry terminals', icon: '⛴️' },
  bus:    { tag: 'highway=bus_stop',    hint: 'bus stops',       icon: '🚌' },
  // car / walk / other → no filter, search everything
}

function buildNominatimUrl(text, travelMethod) {
  const base = `https://nominatim.openstreetmap.org/search`
  const params = new URLSearchParams({
    q: text,
    format: 'json',
    limit: '7',
    addressdetails: '1',
    'accept-language': 'en',
  })
  const f = METHOD_FILTERS[travelMethod]
  if (f) params.set('featuretype', 'settlement') // overridden below with tag
  // Nominatim supports [key=value] bracket syntax in the q param for POI search
  const query = f ? `[${f.tag}] ${text}` : text
  params.set('q', query)
  return `${base}?${params.toString()}`
}

/**
 * Searches Nominatim (OpenStreetMap) and calls onSelect({ place_name, city, country, latitude, longitude })
 * When travelMethod is provided, results are filtered to the relevant infrastructure type.
 */
export default function PlaceSearch({ onSelect, placeholder, label = 'Search place', travelMethod }) {
  const filter = METHOD_FILTERS[travelMethod]
  const defaultPlaceholder = filter
    ? `Search ${filter.hint} (e.g. "Zurich", "London"…)`
    : (placeholder || 'Search for a place…')

  const [query, setQuery]     = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen]       = useState(false)
  const debounceRef           = useRef(null)
  const containerRef          = useRef(null)

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Reset results when method changes
  useEffect(() => {
    setResults([]); setOpen(false); setQuery('')
  }, [travelMethod])

  const handleChange = (text) => {
    setQuery(text)
    clearTimeout(debounceRef.current)
    if (text.length < 3) { setResults([]); setOpen(false); return }

    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const url = buildNominatimUrl(text, travelMethod)
        const r = await fetch(url, { headers: { 'Accept': 'application/json' } })
        const data = await r.json()
        setResults(data)
        setOpen(data.length > 0)
      } catch {
        setResults([])
      } finally {
        setLoading(false)
      }
    }, 400)
  }

  const handleSelect = (result) => {
    const addr = result.address || {}
    const city = addr.city || addr.town || addr.village || addr.suburb || addr.county || ''
    const country = addr.country || ''
    const name = result.name || result.display_name?.split(',')[0]?.trim() || ''

    onSelect({
      place_name: name,
      city,
      country,
      latitude:  parseFloat(parseFloat(result.lat).toFixed(6)),
      longitude: parseFloat(parseFloat(result.lon).toFixed(6)),
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
              {filter.icon} Filtered to {filter.hint}
            </span>
          )}
        </label>
      )}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
        <input
          value={query}
          onChange={e => handleChange(e.target.value)}
          placeholder={defaultPlaceholder}
          className="w-full pl-9 pr-9 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
        {loading && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-primary-500 animate-spin" />
        )}
      </div>

      {open && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 z-50 mt-1 bg-white border border-slate-200 rounded-xl shadow-xl max-h-64 overflow-y-auto">
          {results.map((r, i) => (
            <button
              key={i}
              type="button"
              onClick={() => handleSelect(r)}
              className="w-full flex items-start gap-3 px-4 py-3 hover:bg-primary-50 text-left border-b border-slate-50 last:border-0 transition-colors"
            >
              <MapPin className="w-4 h-4 text-primary-400 flex-shrink-0 mt-0.5" />
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-700 truncate">
                  {r.name || r.display_name?.split(',')[0]}
                </p>
                <p className="text-xs text-slate-400 truncate">{r.display_name}</p>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
