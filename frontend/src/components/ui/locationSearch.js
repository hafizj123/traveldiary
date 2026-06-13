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
  if (options.categories) params.set('categories', options.categories)
  if (options.filter) params.set('filter', options.filter)
  if (options.bias) params.set('bias', options.bias)
  return `https://api.geoapify.com/v1/geocode/autocomplete?${params.toString()}`
}

function classifyNominatimKind(result) {
  const category = (result.category || result.class || '').toLowerCase()
  const type = (result.type || '').toLowerCase()
  const addresstype = (result.addresstype || '').toLowerCase()
  if (category === 'aeroway' || type === 'aerodrome' || type === 'terminal' || addresstype === 'aerodrome') return 'airport'
  if (category === 'aerialway' || ['cable_car', 'gondola', 'chair_lift'].includes(type)) return 'excursion'
  if (category === 'railway' || ['station', 'halt', 'tram_stop', 'subway_entrance'].includes(type) || addresstype === 'station') return 'train'
  if (type === 'bus_stop' || type === 'bus_station' || addresstype === 'bus_stop' || addresstype === 'bus_station') return 'bus'
  if (type === 'ferry_terminal' || addresstype === 'ferry_terminal') return 'ferry'
  return 'location'
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
    country_code: (addr.country_code || '').toUpperCase(),
    latitude: parseFloat(parseFloat(result.lat).toFixed(6)),
    longitude: parseFloat(parseFloat(result.lon).toFixed(6)),
    subtitle: result.display_name,
    result_type: result.type || '',
    addresstype: result.addresstype || '',
    category: result.category || result.class || '',
    place_rank: Number(result.place_rank || 0),
    result_kind: classifyNominatimKind(result),
  }
}

function classifyGeoapifyKind(result) {
  const raw = result.datasource?.raw || {}
  const aeroway = (raw.aeroway || '').toLowerCase()
  const railway = (raw.railway || '').toLowerCase()
  const highway = (raw.highway || '').toLowerCase()
  const amenity = (raw.amenity || '').toLowerCase()
  const publicTransport = (raw.public_transport || '').toLowerCase()
  const resultType = (result.result_type || '').toLowerCase()
  if (aeroway === 'aerodrome' || aeroway === 'terminal' || resultType === 'airport' || raw.iata) return 'airport'
  if (['cable_car', 'gondola', 'chair_lift', 'mixed_lift', 'drag_lift'].includes((raw.aerialway || '').toLowerCase())) return 'excursion'
  if (['station', 'halt', 'tram_stop', 'stop'].includes(railway)) return 'train'
  if (publicTransport === 'station' && !aeroway) return 'train'
  if (highway === 'bus_stop' || amenity === 'bus_station' || amenity === 'bus_stop') return 'bus'
  if (amenity === 'ferry_terminal' || raw.ferry === 'yes') return 'ferry'
  return 'location'
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
    country_code: (result.country_code || '').toUpperCase(),
    latitude: parseFloat(parseFloat(result.lat).toFixed(6)),
    longitude: parseFloat(parseFloat(result.lon).toFixed(6)),
    subtitle: result.formatted || normalizeLocationLabel([primaryName, city, country]),
    result_type: result.result_type || result.rank?.match_type || result.datasource?.raw?.type || '',
    addresstype: result.result_type || result.datasource?.raw?.addresstype || '',
    category: result.datasource?.raw?.category || result.datasource?.raw?.class || '',
    place_rank: Number(result.rank?.importance || result.datasource?.raw?.place_rank || 0),
    result_kind: classifyGeoapifyKind(result),
  }
}

function normalizeChinaCityName(value) {
  return (value || '')
    .replace(/\s*\((city|municipality)\)\s*$/i, '')
    .replace(/\s+(city|municipality)\s*$/i, '')
    .replace(/\s+shi\s*$/i, '')
    .trim()
}

function isChinaCityLevelResult(result) {
  const type = (result.result_type || '').toLowerCase()
  const addresstype = (result.addresstype || '').toLowerCase()
  const category = (result.category || '').toLowerCase()
  const placeRank = Number(result.place_rank || 0)
  const label = normalizeChinaCityName(result.place_name || '')
  const city = normalizeChinaCityName(result.city || '')

  const blockedTypes = new Set([
    'district',
    'suburb',
    'quarter',
    'neighbourhood',
    'neighborhood',
    'county',
    'village',
    'hamlet',
    'town',
    'township',
    'station',
  ])
  if (blockedTypes.has(type) || blockedTypes.has(addresstype)) {
    return false
  }

  if (city && label && city !== label) {
    return false
  }

  const allowedTypes = new Set(['city', 'municipality'])
  if (allowedTypes.has(type) || allowedTypes.has(addresstype)) {
    return true
  }

  return category === 'boundary' || category === 'administrative' || (placeRank > 0 && placeRank <= 16)
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
        iso_code: result.country_code || '',
        latitude: result.latitude,
        longitude: result.longitude,
        result_kind: 'location',
      })
    }
  })

  return Array.from(unique.values())
}

export async function searchCities(text, country) {
  const query = text.trim()
  if (!query) return []
  const normalizedQuery = normalizeChinaCityName(query).toLowerCase()

  const fullQuery = country ? `${query}, ${country}` : query
  const results = await searchPlaceResults(fullQuery, {
    type: 'city',
    nominatimQuery: `place=city ${fullQuery}`,
  })

  const scopedResults = country?.trim().toLowerCase() === 'china'
    ? results.filter((result) => (result.country || '').trim().toLowerCase() === 'china' && isChinaCityLevelResult(result))
    : results

  const unique = new Map()
  scopedResults.forEach((result) => {
    const city = country?.trim().toLowerCase() === 'china'
      ? normalizeChinaCityName(result.place_name || result.city)
      : (result.city || result.place_name)
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
        result_kind: 'location',
      })
    }
  })

  const items = Array.from(unique.values())
  if (country?.trim().toLowerCase() !== 'china') {
    return items
  }

  const exactMatches = items.filter((item) => normalizeChinaCityName(item.city || item.label).toLowerCase() === normalizedQuery)
  if (exactMatches.length > 0) {
    return exactMatches
  }

  const prefixMatches = items.filter((item) => normalizeChinaCityName(item.city || item.label).toLowerCase().startsWith(normalizedQuery))
  if (prefixMatches.length > 0) {
    return prefixMatches
  }

  return items
}
