import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet'
import L from 'leaflet'
import { useEffect, useState, useRef } from 'react'
import { getMethod } from '../../utils/travelIcons'
import { fmtDate } from '../../utils/formatDate'

// ─── Pin icon ─────────────────────────────────────────────────────────────────
function createPin(seq, color = '#4f46e5') {
  return L.divIcon({
    html: `<div style="background:${color};color:#fff;width:28px;height:28px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;"><span style="transform:rotate(45deg)">${seq + 1}</span></div>`,
    iconSize: [28, 28], iconAnchor: [14, 28], popupAnchor: [0, -30], className: '',
  })
}

// ─── Auto-fit bounds (only on first mount, never on re-render) ───────────────
function FitBounds({ points }) {
  const map = useMap()
  const fitted = useRef(false)
  useEffect(() => {
    if (fitted.current) return
    const valid = points.filter(p => p.latitude && p.longitude)
    if (valid.length === 0) return
    map.fitBounds(valid.map(p => [p.latitude, p.longitude]), { padding: [40, 40] })
    fitted.current = true
  }, [points, map])
  return null
}

// ─── Persistent route cache (survives refreshes via localStorage) ─────────────
const LS_KEY = 'td_route_cache_v7'
const _routeCache = new Map(
  (() => { try { return Object.entries(JSON.parse(localStorage.getItem(LS_KEY) || '{}')) } catch { return [] } })()
)
function cacheKey(method, lat1, lon1, lat2, lon2) {
  return `${method}|${lat1.toFixed(5)},${lon1.toFixed(5)}|${lat2.toFixed(5)},${lon2.toFixed(5)}`
}
function persistCache() {
  try {
    const obj = {}
    _routeCache.forEach((v, k) => { obj[k] = v })
    localStorage.setItem(LS_KEY, JSON.stringify(obj))
  } catch {}
}

// ─── Routing helpers ──────────────────────────────────────────────────────────
async function fetchOsrmRoute(lat1, lon1, lat2, lon2, profile) {
  try {
    const url =
      `https://router.project-osrm.org/route/v1/${profile}` +
      `/${lon1},${lat1};${lon2},${lat2}?overview=full&geometries=geojson`
    const r = await fetch(url)
    const d = await r.json()
    if (d.code === 'Ok' && d.routes?.[0]) {
      return d.routes[0].geometry.coordinates.map(([lon, lat]) => [lat, lon])
    }
  } catch {}
  return null
}

/** Great-circle arc for flights */
function greatCirclePoints(lat1, lon1, lat2, lon2, n = 60) {
  const toRad = d => d * Math.PI / 180
  const toDeg = r => r * 180 / Math.PI
  const φ1 = toRad(lat1), λ1 = toRad(lon1)
  const φ2 = toRad(lat2), λ2 = toRad(lon2)
  const d = 2 * Math.asin(Math.sqrt(
    Math.sin((φ2 - φ1) / 2) ** 2 +
    Math.cos(φ1) * Math.cos(φ2) * Math.sin((λ2 - λ1) / 2) ** 2
  ))
  if (d < 0.01) return [[lat1, lon1], [lat2, lon2]]
  const pts = []
  for (let i = 0; i <= n; i++) {
    const f = i / n
    const A = Math.sin((1 - f) * d) / Math.sin(d)
    const B = Math.sin(f * d) / Math.sin(d)
    const x = A * Math.cos(φ1) * Math.cos(λ1) + B * Math.cos(φ2) * Math.cos(λ2)
    const y = A * Math.cos(φ1) * Math.sin(λ1) + B * Math.cos(φ2) * Math.sin(λ2)
    const z = A * Math.sin(φ1) + B * Math.sin(φ2)
    pts.push([toDeg(Math.atan2(z, Math.sqrt(x * x + y * y))), toDeg(Math.atan2(y, x))])
  }
  return pts
}

/** Quadratic Bézier arc — fallback for ferry / unknown */
function bezierCurve(lat1, lon1, lat2, lon2, n = 40) {
  const dlat = lat2 - lat1, dlon = lon2 - lon1
  const len = Math.sqrt(dlat * dlat + dlon * dlon) || 1
  const off = len * 0.25
  const cx = (lat1 + lat2) / 2 - (dlon / len) * off
  const cy = (lon1 + lon2) / 2 + (dlat / len) * off
  const pts = []
  for (let i = 0; i <= n; i++) {
    const t = i / n
    pts.push([
      (1 - t) ** 2 * lat1 + 2 * (1 - t) * t * cx + t ** 2 * lat2,
      (1 - t) ** 2 * lon1 + 2 * (1 - t) * t * cy + t ** 2 * lon2,
    ])
  }
  return pts
}

async function fetchTrainRoute(from, to, seg) {
  if (Array.isArray(seg?.route_geometry) && seg.route_geometry.length > 1) {
    return seg.route_geometry
  }
  return null
}

async function computeRoute(from, to, seg) {
  const method = seg?.travel_method || 'other'
  const straight = [[from.latitude, from.longitude], [to.latitude, to.longitude]]
  if (!from.latitude || !to.latitude) return straight

  const ck = cacheKey(method, from.latitude, from.longitude, to.latitude, to.longitude)
  if (method !== 'train' && _routeCache.has(ck)) return _routeCache.get(ck)

  let result
  switch (method) {
    case 'flight':
      result = greatCirclePoints(from.latitude, from.longitude, to.latitude, to.longitude)
      break
    case 'train': {
      const r = await fetchTrainRoute(from, to, seg)
      if (r) {
        _routeCache.set(ck, r)
        persistCache()
        return r
      }
      return null
    }
    case 'ferry':
      result = bezierCurve(from.latitude, from.longitude, to.latitude, to.longitude)
      break
    case 'car':
    case 'bus': {
      const r = await fetchOsrmRoute(from.latitude, from.longitude, to.latitude, to.longitude, 'driving')
      result = r || straight
      break
    }
    case 'walk': {
      const r = await fetchOsrmRoute(from.latitude, from.longitude, to.latitude, to.longitude, 'foot')
      result = r || straight
      break
    }
    default:
      result = straight
  }

  _routeCache.set(ck, result)
  persistCache()
  return result
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function TripMap({ points = [], segments = [] }) {
  const [routes, setRoutes] = useState(() => {
    const seed = {}
    const valid = points.filter(p => p.latitude && p.longitude)
    const sMap = {}
    segments.forEach(s => { sMap[`${s.from_point_id}-${s.to_point_id}`] = s })
    for (let i = 0; i < valid.length - 1; i++) {
      const a = valid[i], b = valid[i + 1]
      const seg = sMap[`${a.id}-${b.id}`]
      if (Array.isArray(seg?.route_geometry) && seg.route_geometry.length > 1) {
        seed[`${a.id}-${b.id}`] = seg.route_geometry
        continue
      }
      const method = seg?.travel_method || 'other'
      if (method === 'train') continue
      const ck = cacheKey(method, a.latitude, a.longitude, b.latitude, b.longitude)
      if (_routeCache.has(ck)) seed[`${a.id}-${b.id}`] = _routeCache.get(ck)
    }
    return seed
  })

  const validPoints = points.filter(p => p.latitude && p.longitude)

  const segMap = {}
  segments.forEach(s => { segMap[`${s.from_point_id}-${s.to_point_id}`] = s })

  useEffect(() => {
    if (validPoints.length < 2) return
    let cancelled = false
    ;(async () => {
      const computed = {}
      for (let i = 0; i < validPoints.length - 1; i++) {
        const a = validPoints[i], b = validPoints[i + 1]
        const seg = segMap[`${a.id}-${b.id}`]
        const key = `${a.id}-${b.id}`
        const r = await computeRoute(a, b, seg)
        if (r) computed[key] = r
      }
      if (!cancelled) {
        setRoutes(prev => ({ ...prev, ...computed }))
      }
    })()
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [validPoints.map(p => p.id).join(','), segments.map(s => s.id).join(',')])

  if (!validPoints.length) {
    return (
      <div className="flex items-center justify-center h-full bg-slate-100 rounded-xl text-slate-400">
        No locations added yet
      </div>
    )
  }

  const center = [validPoints[0].latitude, validPoints[0].longitude]

  return (
    <MapContainer center={center} zoom={5} className="w-full h-full rounded-xl">
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />
      <FitBounds points={validPoints} />

      {validPoints.map((pt, i) => {
        if (i >= validPoints.length - 1) return null
        const next = validPoints[i + 1]
        const key  = `${pt.id}-${next.id}`
        const seg  = segMap[key]
        const method = getMethod(seg?.travel_method || 'other')
        const positions = routes[key] || [[pt.latitude, pt.longitude], [next.latitude, next.longitude]]
        const isTrainFallback = seg?.travel_method === 'train' && !routes[key]
        return (
          <Polyline
            key={key}
            positions={positions}
            pathOptions={isTrainFallback ? {
              color: '#475569',
              weight: 3,
              dashArray: '8,6',
              opacity: 0.9,
            } : {
              color:     method.color,
              weight:    seg?.travel_method === 'flight' ? 2 : 3,
              dashArray: method.lineStyle ? method.lineStyle.join(',') : null,
              opacity:   0.85,
            }}
          />
        )
      })}

      {validPoints.map((pt, i) => (
        <Marker key={pt.id} position={[pt.latitude, pt.longitude]} icon={createPin(i)}>
          <Popup maxWidth={240}>
            <div className="space-y-1 text-sm">
              <p className="font-semibold">{pt.place_name}</p>
              <p className="text-slate-500">{pt.city ? `${pt.city}, ` : ''}{pt.country}</p>
              <p className="text-slate-500">{fmtDate(pt.visit_date)}</p>
              {pt.image_url && (
                <img src={pt.image_url} alt={pt.place_name} className="w-full h-28 object-cover rounded mt-2" />
              )}
              {pt.weather_data && (
                <div className="flex items-center gap-1 text-slate-500 text-xs mt-1">
                  <img src={`https://openweathermap.org/img/wn/${pt.weather_data.icon}.png`} alt="" className="w-6 h-6" />
                  <span>
                    {pt.weather_data.temp_max != null
                      ? `${pt.weather_data.temp_min}–${pt.weather_data.temp_max}°C`
                      : `${Math.round(pt.weather_data.temp || 0)}°C`}
                    {' · '}{pt.weather_data.description}
                  </span>
                </div>
              )}
              {pt.description && (
                <p className="text-slate-600 text-xs mt-1 line-clamp-2">{pt.description}</p>
              )}
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  )
}
