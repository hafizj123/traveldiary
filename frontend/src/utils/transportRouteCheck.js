import { routesApi } from '../api/routes'

const MAX_DISTANCE_KM = {
  car: 2000,
  bus: 2000,
  walk: 100,
  other: 2000,
}

const ORIGIN_PROXIMITY_METERS = {
  flight: 200,
  ferry: 500,
  excursion: 400,
}

const NAME_HINT_PATTERNS = {
  ferry: [
    /\bferry\b/i,
    /\bterminal\b/i,
    /\bport\b/i,
    /\bpier\b/i,
    /\bharbou?r\b/i,
    /\bwharf\b/i,
    /\bjetty\b/i,
    /\bdock\b/i,
  ],
  excursion: [
    /\blift\b/i,
    /\bchair[\s-]?lift\b/i,
    /\bgondola\b/i,
    /\bcable\s+car\b/i,
    /\bfunicular\b/i,
    /\bropeway\b/i,
    /\baerialway\b/i,
    /\btelecabine\b/i,
    /\btelepherique\b/i,
    /\bski\s+lift\b/i,
  ],
}

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371
  const dLat = (lat2 - lat1) * (Math.PI / 180)
  const dLon = (lon2 - lon1) * (Math.PI / 180)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * (Math.PI / 180)) *
      Math.cos(lat2 * (Math.PI / 180)) *
      Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

function formatDistance(distanceMeters) {
  if (!Number.isFinite(distanceMeters)) return ''
  if (distanceMeters >= 1000) {
    return `${Math.round(distanceMeters / 100) / 10} km`
  }
  return `${Math.round(distanceMeters)} m`
}

function looksLikeOriginTerminal(point, method) {
  const patterns = NAME_HINT_PATTERNS[method] || []
  if (patterns.length === 0) return false
  const haystack = [point?.place_name, point?.description].filter(Boolean).join(' ')
  return patterns.some((pattern) => pattern.test(haystack))
}

async function fetchOsrmRouteExists(lat1, lon1, lat2, lon2, profile) {
  try {
    const url =
      `https://router.project-osrm.org/route/v1/${profile}` +
      `/${lon1},${lat1};${lon2},${lat2}?overview=false`
    const response = await fetch(url)
    const data = await response.json()
    return data.code === 'Ok' && Array.isArray(data.routes) && data.routes.length > 0
  } catch {
    return false
  }
}

async function checkOriginTransportPlace({
  method,
  fromPoint,
  thresholdMeters,
  fallbackMessage,
  behavior = 'confirm',
}) {
  if (!fromPoint || looksLikeOriginTerminal(fromPoint, method)) {
    return null
  }

  try {
    const result = await routesApi.nearestTransportPlace({
      lat: Number(fromPoint.latitude),
      lon: Number(fromPoint.longitude),
      method,
      country: fromPoint.country || undefined,
    })
    const place = result?.place

    if (place && typeof place.distance_meters === 'number') {
      if (place.distance_meters <= thresholdMeters) {
        return null
      }

      return {
        exists: true,
        behavior,
        message: `${fallbackMessage} Nearest match is ${formatDistance(place.distance_meters)} away.`,
      }
    }
  } catch {
    return null
  }

  return {
    exists: true,
    behavior,
    message: fallbackMessage,
  }
}

function buildStationPayload(station) {
  if (!station) {
    return undefined
  }

  const latitude = Number(station.latitude)
  const longitude = Number(station.longitude)
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    return undefined
  }

  return {
    place_name: station.place_name || station.name || '',
    city: station.city || '',
    country: station.country || '',
    latitude,
    longitude,
  }
}

export async function checkTransportRouteBeforeSave({ method, fromPoint, toPoint, fromStation, toStation }) {
  if (!method || !fromPoint || !toPoint) {
    return { exists: true, behavior: 'allow', message: '' }
  }

  const lat1 = Number(fromPoint.latitude)
  const lon1 = Number(fromPoint.longitude)
  const lat2 = Number(toPoint.latitude)
  const lon2 = Number(toPoint.longitude)

  if (![lat1, lon1, lat2, lon2].every(Number.isFinite)) {
    return { exists: true, behavior: 'allow', message: '' }
  }

  const maxKm = MAX_DISTANCE_KM[method]
  if (maxKm !== undefined) {
    const distKm = Math.round(haversineKm(lat1, lon1, lat2, lon2))
    if (distKm > maxKm) {
      return {
        exists: false,
        behavior: 'block',
        message: `This location is approximately ${distKm.toLocaleString()} km from your previous stop. That is too far for ${method.charAt(0).toUpperCase() + method.slice(1)}. Please choose a closer destination or switch to a different transport method such as Flight.`,
      }
    }
  }

  if (method === 'car' || method === 'bus' || method === 'walk') {
    const profile = method === 'walk' ? 'foot' : 'driving'
    const exists = await fetchOsrmRouteExists(lat1, lon1, lat2, lon2, profile)
    return {
      exists,
      behavior: exists ? 'allow' : 'confirm',
      message: exists ? '' : `No ${method} route was found between these two locations. If you continue, we will draw a fallback line.`,
    }
  }

  if (method === 'other') {
    return { exists: true, behavior: 'allow', message: '' }
  }

  if (method === 'flight') {
    try {
      const result = await routesApi.nearestTransportPlace({ lat: lat1, lon: lon1, method: 'flight', country: fromPoint.country || undefined })
      const place = result?.place
      if (place && typeof place.distance_meters === 'number' && place.distance_meters > ORIGIN_PROXIMITY_METERS.flight) {
        return {
          exists: true,
          behavior: 'confirm',
          message: `Your previous stop does not appear to be at an airport. Nearest airport is ${formatDistance(place.distance_meters)} away. Are you sure you want to continue?`,
        }
      }
    } catch {
      // If the check fails, allow without warning.
    }
    return { exists: true, behavior: 'allow', message: '' }
  }

  if (method === 'ferry') {
    const originCheck = await checkOriginTransportPlace({
      method: 'ferry',
      fromPoint,
      thresholdMeters: ORIGIN_PROXIMITY_METERS.ferry,
      fallbackMessage: 'Your previous stop is not a ferry terminal, port, or pier. Ferry segments must start from a ferry terminal.',
      behavior: 'block',
    })
    if (originCheck) {
      return originCheck
    }
  }

  if (method === 'excursion') {
    const originCheck = await checkOriginTransportPlace({
      method: 'excursion',
      fromPoint,
      thresholdMeters: ORIGIN_PROXIMITY_METERS.excursion,
      fallbackMessage: 'Your previous stop does not appear to be a lift station. Excursion segments should start from a lift station. Are you sure you want to continue?',
    })
    if (originCheck) {
      return originCheck
    }
  }

  return routesApi.checkRoute({
    method,
    lat1,
    lon1,
    lat2,
    lon2,
    country1: fromPoint.country || undefined,
    country2: toPoint.country || undefined,
    from_station: buildStationPayload(fromStation),
    to_station: buildStationPayload(toStation),
  })
}
