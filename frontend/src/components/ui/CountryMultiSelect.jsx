import { useEffect, useRef, useState } from 'react'
import { Search, X } from 'lucide-react'
import { searchCountries } from './locationSearch'
import LoadingSpinner from './LoadingSpinner'

export default function CountryMultiSelect({
  label,
  value = [],
  onChange,
  error = '',
  placeholder = 'Search countries to add',
  disabled = false,
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const debounceRef = useRef(null)
  const containerRef = useRef(null)

  useEffect(() => {
    const onDocClick = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  const selectedKeys = new Set((value || []).map((item) => item.toLowerCase()))

  const handleSearch = (nextQuery) => {
    setQuery(nextQuery)
    clearTimeout(debounceRef.current)
    if (disabled || nextQuery.trim().length < 1) {
      setResults([])
      setOpen(false)
      return
    }

    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const matches = await searchCountries(nextQuery)
        const filtered = matches.filter((item) => !selectedKeys.has((item.country || item.label || '').toLowerCase()))
        setResults(filtered)
        setOpen(filtered.length > 0)
      } catch {
        setResults([])
        setOpen(false)
      } finally {
        setLoading(false)
      }
    }, 250)
  }

  const addCountry = (country) => {
    const normalized = (country || '').trim()
    if (!normalized || selectedKeys.has(normalized.toLowerCase())) return
    onChange([...(value || []), normalized])
    setQuery('')
    setResults([])
    setOpen(false)
  }

  const removeCountry = (country) => {
    onChange((value || []).filter((item) => item.toLowerCase() !== country.toLowerCase()))
  }

  return (
    <div ref={containerRef} className="space-y-2">
      {label ? <label className="block text-sm font-medium text-slate-700">{label}</label> : null}
      <div className="flex flex-wrap gap-2">
        {(value || []).map((country) => (
          <span key={country} className="inline-flex items-center gap-1 rounded-full bg-primary-50 px-3 py-1 text-xs font-medium text-primary-700">
            {country}
            <button type="button" onClick={() => removeCountry(country)} disabled={disabled} className="text-primary-500 hover:text-primary-700">
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          value={query}
          onChange={(event) => handleSearch(event.target.value)}
          onFocus={() => {
            if (results.length > 0) setOpen(true)
          }}
          placeholder={placeholder}
          disabled={disabled}
          className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-9 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:cursor-not-allowed disabled:bg-slate-50"
        />
        {loading ? <LoadingSpinner size="sm" className="absolute right-3 top-1/2 -translate-y-1/2" /> : null}
      </div>
      {open && results.length > 0 ? (
        <div className="max-h-56 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-xl">
          {results.map((result) => (
            <button
              key={result.id}
              type="button"
              onClick={() => addCountry(result.country || result.label)}
              className="block w-full border-b border-slate-50 px-4 py-3 text-left hover:bg-primary-50 last:border-b-0"
            >
              <p className="text-sm font-medium text-slate-700">{result.country || result.label}</p>
              {result.subtitle ? <p className="text-xs text-slate-400 truncate">{result.subtitle}</p> : null}
            </button>
          ))}
        </div>
      ) : null}
      {error ? <p className="text-sm text-rose-600">{error}</p> : null}
    </div>
  )
}
