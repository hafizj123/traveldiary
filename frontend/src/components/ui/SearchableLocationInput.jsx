import { useEffect, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { getLocationResultIcon, getLocationResultKind } from './locationResultIcon'
import LoadingSpinner from './LoadingSpinner'

export default function SearchableLocationInput({
  label,
  value,
  onChange,
  onSelect,
  searchFn,
  placeholder,
  required = false,
  disabled = false,
  minChars = 2,
  minLoadingMs = 0,
}) {
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const debounceRef = useRef(null)
  const containerRef = useRef(null)

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  useEffect(() => () => clearTimeout(debounceRef.current), [])

  const handleInputChange = (nextValue) => {
    onChange(nextValue)
    clearTimeout(debounceRef.current)

    if (nextValue.trim().length < minChars || disabled) {
      setResults([])
      setOpen(false)
      return
    }

    debounceRef.current = setTimeout(async () => {
      const startedAt = Date.now()
      setLoading(true)
      try {
        const nextResults = await searchFn(nextValue)
        const remainingMs = Math.max(0, minLoadingMs - (Date.now() - startedAt))
        if (remainingMs > 0) {
          await new Promise((resolve) => window.setTimeout(resolve, remainingMs))
        }
        setResults(nextResults)
        setOpen(nextResults.length > 0)
      } catch {
        setResults([])
        setOpen(false)
      } finally {
        setLoading(false)
      }
    }, 300)
  }

  const handleSelect = (result) => {
    onChange(result.label)
    onSelect?.(result)
    setResults([])
    setOpen(false)
  }

  return (
    <div ref={containerRef} className="relative">
      {label && (
        <label className="block text-sm font-medium text-slate-700 mb-1">
          {label}
        </label>
      )}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
        <input
          value={value}
          onChange={(e) => handleInputChange(e.target.value)}
          onFocus={() => {
            if (results.length > 0) setOpen(true)
          }}
          placeholder={placeholder}
          required={required}
          disabled={disabled}
          autoComplete="off"
          className="w-full pl-9 pr-9 py-2 text-base sm:text-sm text-slate-800 caret-slate-800 placeholder:text-slate-400 selection:bg-primary-100 selection:text-slate-900 border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:bg-slate-50 disabled:text-slate-500 disabled:cursor-not-allowed"
          style={{
            color: '#1e293b',
            WebkitTextFillColor: '#1e293b',
            caretColor: '#1e293b',
          }}
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
            const Icon = getLocationResultIcon(getLocationResultKind(result))
            return (
              <button
                key={result.id}
                type="button"
                onClick={() => handleSelect(result)}
                className="w-full flex items-start gap-3 px-4 py-3 text-left text-slate-800 hover:bg-primary-50 active:bg-primary-100 border-b border-slate-50 last:border-0 transition-colors"
              >
                <Icon className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary-400" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-700 truncate">{result.label}</p>
                  {result.subtitle && (
                    <p className="text-xs text-slate-400 truncate">{result.subtitle}</p>
                  )}
                </div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
