import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import { Link } from 'react-router-dom'
import L from 'leaflet'
import { useEffect, useRef } from 'react'
import { DEFAULT_MAP_PROPS, DEFAULT_TILE_PROPS } from './mapConfig'

const countryDot = L.divIcon({
  html: `<div style="background:#4f46e5;width:14px;height:14px;border-radius:50%;border:2.5px solid white;box-shadow:0 2px 6px rgba(0,0,0,.45)"></div>`,
  iconSize: [14, 14], iconAnchor: [7, 7], className: '',
})

function FitBounds({ coords }) {
  const map = useMap()
  const fitted = useRef(false)
  useEffect(() => {
    if (fitted.current || !coords.length) return
    if (coords.length === 1) { map.setView(coords[0], 5); fitted.current = true; return }
    map.fitBounds(coords, { padding: [30, 30] })
    fitted.current = true
  }, [coords, map])
  return null
}

export default function MiniMap({ points = [], trips = [] }) {
  const valid = points.filter(p => p.latitude && p.longitude && p.country)
  if (!valid.length) return (
    <div className="flex items-center justify-center h-full bg-slate-100 text-slate-400 text-sm">
      No locations yet
    </div>
  )

  // Group points by country
  const byCountry = {}
  valid.forEach(pt => {
    if (!byCountry[pt.country]) byCountry[pt.country] = []
    byCountry[pt.country].push(pt)
  })

  // One entry per country: pick rep point with image if possible
  const entries = Object.entries(byCountry).map(([country, pts]) => {
    const rep = pts.find(p => p.image_url) || pts[0]
    const tripIds = new Set(pts.map(p => p.trip_id))
    const relatedTrips = trips.filter(t => tripIds.has(t.id))
    return { country, rep, pts, relatedTrips }
  })

  const coords = entries.map(e => [e.rep.latitude, e.rep.longitude])

  return (
    <MapContainer
      center={[20, 10]}
      zoom={2}
      className="w-full h-full"
      zoomControl
      attributionControl={false}
      {...DEFAULT_MAP_PROPS}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        {...DEFAULT_TILE_PROPS}
      />
      <FitBounds coords={coords} />

      {entries.map(({ country, rep, pts, relatedTrips }) => (
        <Marker key={country} position={[rep.latitude, rep.longitude]} icon={countryDot}>
          <Popup maxWidth={220} className="country-popup">
            <div className="space-y-2 text-sm" style={{ minWidth: 180 }}>
              {rep.image_url && (
                <img src={rep.image_url} alt={country} className="w-full h-24 object-cover rounded" style={{ display: 'block' }} />
              )}
              <p className="font-semibold text-slate-800 text-base">{country}</p>
              <p className="text-xs text-slate-400">{pts.length} place{pts.length !== 1 ? 's' : ''} visited</p>
              {relatedTrips.length > 0 && (
                <div className="space-y-1 pt-1 border-t border-slate-100">
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Trips</p>
                  {relatedTrips.map(t => (
                    <Link key={t.id} to={`/trips/${t.id}`}
                      className="block text-xs text-primary-600 hover:text-primary-800 hover:underline truncate">
                      → {t.title}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  )
}
