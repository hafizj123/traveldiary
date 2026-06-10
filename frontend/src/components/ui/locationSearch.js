const GEOAPIFY_KEY = import.meta.env.VITE_GEOAPIFY_API_KEY

export function normalizeLocationLabel(parts) {
  return parts.filter(Boolean).join(', ')
}

function buildNominatimUrl(text, nominatimQuery) {
  const params = new URLSearchParams({
    q: nominatimQuery || text,
    format: 'jsonv2',
    limit: '10',
    addressdetails: '1',
    namedetails: '1',
    dedupe: '1',
    'accept-language': 'en',
  })
  return `https://nominatim.openstreetmap.org/search?${params.toString()}`
}

function buildGeoapifyUrl(text, options = {}) {
  const params = new URLSearchParams({
    text,
    format: 'json',
    limit: '10',
    lang: 'en',
    apiKey: GEOAPIFY_KEY,
  })
  if (options.type) params.set('type', options.type)
  if (options.filter) params.set('filter', options.filter)
  if (options.bias) params.set('bias', options.bias)
  return `https://api.geoapify.com/v1/geocode/autocomplete?${params.toString()}`
}

function mapNominatimResult(result) {
  const addr = result.address || {}
  const city = addr.city || addr.town || addr.village || addr.suburb || addr.county || ''
  const country = addr.country || ''
  const englishName = result.namedetails?.['name:en']
  const primaryName = englishName || result.namedetails?.name || result.name || result.display_name?.split(',')[0]?.trim() || ''

  return {
    id: result.place_id,
    place_name: primaryName,
    city,
    country,
    latitude: parseFloat(parseFloat(result.lat).toFixed(6)),
    longitude: parseFloat(parseFloat(result.lon).toFixed(6)),
    subtitle: result.display_name,
  }
}

function mapGeoapifyResult(result) {
  const city = result.city || result.town || result.village || result.suburb || result.county || ''
  const country = result.country || ''
  const primaryName = result.name || result.address_line1 || result.formatted?.split(',')[0]?.trim() || ''

  return {
    id: result.place_id || `${result.lat}-${result.lon}-${primaryName}`,
    place_name: primaryName,
    city,
    country,
    latitude: parseFloat(parseFloat(result.lat).toFixed(6)),
    longitude: parseFloat(parseFloat(result.lon).toFixed(6)),
    subtitle: result.formatted || normalizeLocationLabel([primaryName, city, country]),
  }
}

export async function searchPlaceResults(text, options = {}) {
  if (GEOAPIFY_KEY) {
    const response = await fetch(buildGeoapifyUrl(text, options), {
      headers: { Accept: 'application/json' },
    })
    const data = await response.json()
    return (data.results || []).map(mapGeoapifyResult)
  }

  const response = await fetch(buildNominatimUrl(text, options.nominatimQuery), {
    headers: { Accept: 'application/json' },
  })
  const data = await response.json()
  return Array.isArray(data) ? data.map(mapNominatimResult) : []
}

export async function searchCountries(text) {
  const query = text.trim()
  if (!query) return []

  const results = await searchPlaceResults(query, {
    type: 'country',
    nominatimQuery: `place=country ${query}`,
  })

  const unique = new Map()
  results.forEach((result) => {
    if (!result.country) return
    if (!unique.has(result.country)) {
      unique.set(result.country, {
        id: `country-${result.country}`,
        label: result.country,
        subtitle: result.subtitle,
        country: result.country,
        latitude: result.latitude,
        longitude: result.longitude,
      })
    }
  })

  return Array.from(unique.values())
}

export async function searchCities(text, country) {
  const query = text.trim()
  if (!query) return []

  const fullQuery = country ? `${query}, ${country}` : query
  const results = await searchPlaceResults(fullQuery, {
    type: 'city',
    nominatimQuery: `place=city ${fullQuery}`,
  })

  const unique = new Map()
  results.forEach((result) => {
    const city = result.city || result.place_name
    if (!city) return
    const key = `${city}|${result.country}`
    if (!unique.has(key)) {
      unique.set(key, {
        id: `city-${key}`,
        label: city,
        subtitle: normalizeLocationLabel([result.country, result.subtitle]),
        city,
        country: result.country,
        latitude: result.latitude,
        longitude: result.longitude,
      })
    }
  })

  return Array.from(unique.values())
}
