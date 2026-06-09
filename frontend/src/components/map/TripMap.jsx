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

// ─── Train routing — Overpass + Dijkstra (client-side) ───────────────────────
function _haversineM(lat1, lon1, lat2, lon2) {
  const R = 6_371_000
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLon = (lon2 - lon1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

function _nearestNode(nodes, graph, lat, lon) {
  let bestId = null, bestD = Infinity
  // Only consider nodes that are actually connected in the graph
  for (const id of Object.keys(graph)) {
    const pos = nodes[id]
    if (!pos) continue
    const d = _haversineM(lat, lon, pos[0], pos[1])
    if (d < bestD) { bestD = d; bestId = id }
  }
  return bestId
}

function _dijkstra(graph, start, end) {
  const dist = {}, prev = {}
  const queue = [[0, start]]
  for (const id of Object.keys(graph)) dist[id] = Infinity
  dist[start] = 0
  while (queue.length) {
    queue.sort((a, b) => a[0] - b[0])
    const [d, cur] = queue.shift()
    if (cur == end) break
    if (d > dist[cur]) continue
    for (const [nb, w] of (graph[cur] || [])) {
      const nd = d + w
      if (nd < (dist[nb] ?? Infinity)) {
        dist[nb] = nd; prev[nb] = cur
        queue.push([nd, nb])
      }
    }
  }
  const path = []
  let cur = end
  while (cur != null) { path.unshift(cur); cur = prev[cur] }
  return path[0] == start ? path : []
}

// Deduplicate simultaneous identical Overpass requests (React StrictMode fires effects twice)
const _inFlight = new Map()

async function fetchTrainRoute(lat1, lon1, lat2, lon2) {
  const latD = Math.abs(lat2 - lat1)
  const lonD = Math.abs(lon2 - lon1)
  console.log('[train] bbox delta:', latD, lonD)
  if (latD > 8 || lonD > 12) { console.log('[train] bbox too large'); return null }

  const margin = Math.max(latD, lonD) * 0.2 + 0.4
  const S = (Math.min(lat1, lat2) - margin).toFixed(4)
  const N = (Math.max(lat1, lat2) + margin).toFixed(4)
  const W = (Math.min(lon1, lon2) - margin).toFixed(4)
  const E = (Math.max(lon1, lon2) + margin).toFixed(4)
  const flightKey = `${S},${W},${N},${E}`

  if (_inFlight.has(flightKey)) {
    console.log('[train] reusing in-flight request')
    return _inFlight.get(flightKey)
  }

  const query = `[out:json][timeout:90];
(
  way["railway"="rail"](${S},${W},${N},${E});
);
(._;>;);
out body;`

  console.log('[train] Overpass query bbox:', S, W, N, E)

  const doFetch = async () => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 95_000) // 95 s hard cap
    try {
      const res = await fetch('https://overpass-api.de/api/interpreter', {
        method: 'POST', body: query, signal: controller.signal,
      })
      if (res.status === 429) return null   // signal retry
      console.log('[train] Overpass status:', res.status)
      if (!res.ok) return false             // hard fail
      return res.json()
    } catch (e) {
      if (e.name === 'AbortError') { console.log('[train] fetch timed out'); return null }
      throw e
    } finally {
      clearTimeout(timer)
    }
  }

  const promise = (async () => {
    try {
      let data = await doFetch()
      // Keep retrying on 429 or timeout (null), up to 5 attempts, 10 s apart
      let attempts = 1
      while (data === null && attempts < 5) {
        console.log(`[train] attempt ${attempts} failed, retrying in 10s...`)
        await new Promise(r => setTimeout(r, 10_000))
        data = await doFetch()
        attempts++
      }
      if (!data) return null
      console.log('[train] elements:', data.elements?.length)

      const nodes = {}
      const ways  = []
      data.elements.forEach(el => {
        if (el.type === 'node') nodes[String(el.id)] = [el.lat, el.lon]
        if (el.type === 'way' && el.nodes) ways.push(el.nodes)
      })
      console.log('[train] nodes:', Object.keys(nodes).length, 'ways:', ways.length)

      const graph = {}
      ways.forEach(wayNodes => {
        for (let i = 0; i < wayNodes.length - 1; i++) {
          const a = String(wayNodes[i]), b = String(wayNodes[i + 1])
          if (!nodes[a] || !nodes[b]) continue
          const d = _haversineM(nodes[a][0], nodes[a][1], nodes[b][0], nodes[b][1])
          if (!graph[a]) graph[a] = []
          if (!graph[b]) graph[b] = []
          graph[a].push([b, d])
          graph[b].push([a, d])
        }
      })
      console.log('[train] graph nodes:', Object.keys(graph).length)

      if (!Object.keys(graph).length) { console.log('[train] empty graph'); return null }

      const startId = _nearestNode(nodes, graph, lat1, lon1)
      const endId   = _nearestNode(nodes, graph, lat2, lon2)
      console.log('[train] startId:', startId, 'inGraph:', !!graph[startId])
      console.log('[train] endId:  ', endId,   'inGraph:', !!graph[endId])
      if (!startId || !endId || startId === endId) return null

      const path = _dijkstra(graph, startId, endId)
      console.log('[train] path length:', path.length)
      if (!path.length) return null

      return [
        [lat1, lon1],
        ...path.map(id => nodes[id]),
        [lat2, lon2],
      ]
    } catch (e) {
      console.error('[train] error:', e)
      return null
    }
  })()

  _inFlight.set(flightKey, promise)
  promise.finally(() => _inFlight.delete(flightKey))
  return promise
}

async function computeRoute(from, to, method) {
  const straight = [[from.latitude, from.longitude], [to.latitude, to.longitude]]
  if (!from.latitude || !to.latitude) return straight

  const ck = cacheKey(method, from.latitude, from.longitude, to.latitude, to.longitude)
  console.log('[route] method:', method, 'cacheHit:', _routeCache.has(ck))
  if (_routeCache.has(ck)) return _routeCache.get(ck)

  let result
  switch (method) {
    case 'flight':
      result = greatCirclePoints(from.latitude, from.longitude, to.latitude, to.longitude)
      break
    case 'train': {
      const r = await fetchTrainRoute(from.latitude, from.longitude, to.latitude, to.longitude)
      if (r) {
        _routeCache.set(ck, r)
        persistCache()
        return r
      }
      // Return null so the caller knows this specific route failed
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
  // Seed from module-level cache so remounts (tab switching) are instant
  const [routes, setRoutes] = useState(() => {
    const seed = {}
    const valid = points.filter(p => p.latitude && p.longitude)
    const sMap = {}
    segments.forEach(s => { sMap[`${s.from_point_id}-${s.to_point_id}`] = s })
    for (let i = 0; i < valid.length - 1; i++) {
      const a = valid[i], b = valid[i + 1]
      const method = sMap[`${a.id}-${b.id}`]?.travel_method || 'other'
      const ck = cacheKey(method, a.latitude, a.longitude, b.latitude, b.longitude)
      if (_routeCache.has(ck)) seed[`${a.id}-${b.id}`] = _routeCache.get(ck)
    }
    return seed
  })
  // Keys of train segments where Overpass failed — rendered dashed until retry succeeds
  const [failedKeys, setFailedKeys] = useState(new Set())

  const validPoints = points.filter(p => p.latitude && p.longitude)

  const segMap = {}
  segments.forEach(s => { segMap[`${s.from_point_id}-${s.to_point_id}`] = s })

  useEffect(() => {
    if (validPoints.length < 2) return
    let cancelled = false
    ;(async () => {
      const computed = {}
      let failed   = new Set()
      for (let i = 0; i < validPoints.length - 1; i++) {
        const a = validPoints[i], b = validPoints[i + 1]
        const seg = segMap[`${a.id}-${b.id}`]
        const key = `${a.id}-${b.id}`
        const r = await computeRoute(a, b, seg?.travel_method || 'other')
        if (r === null) {
          failed.add(key)   // train fetch failed — mark for retry
        } else {
          computed[key] = r
        }
      }
      if (!cancelled) {
        setRoutes(prev => ({ ...prev, ...computed }))
        setFailedKeys(failed)
      }

      // Auto-retry failed train routes every 60 s until success or component unmounts
      while (failed.size > 0 && !cancelled) {
        await new Promise(r => setTimeout(r, 60_000))
        if (cancelled) return
        const retried = {}
        const stillFailed = new Set()
        for (const key of failed) {
          const [aid, bid] = key.split('-').map(Number)
          const a = validPoints.find(p => p.id === aid)
          const b = validPoints.find(p => p.id === bid)
          if (!a || !b) continue
          const seg = segMap[key]
          const r = await computeRoute(a, b, seg?.travel_method || 'other')
          if (r === null) stillFailed.add(key)
          else retried[key] = r
        }
        if (!cancelled) {
          setRoutes(prev => ({ ...prev, ...retried }))
          setFailedKeys(stillFailed)
          failed = stillFailed  // update loop variable
        }
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
        const isFailed = failedKeys.has(key)
        const positions = routes[key] || [[pt.latitude, pt.longitude], [next.latitude, next.longitude]]
        return (
          <Polyline
            key={key}
            positions={positions}
            pathOptions={isFailed ? {
              color: '#94a3b8',
              weight: 2,
              dashArray: '6,6',
              opacity: 0.5,
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
