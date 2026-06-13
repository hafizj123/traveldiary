import { MapContainer, TileLayer, Marker, useMapEvents, useMap } from 'react-leaflet'
import L from 'leaflet'
import { useState, useEffect } from 'react'
import { MapPin } from 'lucide-react'
import LoadingSpinner from '../ui/LoadingSpinner'
import { DEFAULT_MAP_PROPS, DEFAULT_TILE_PROPS } from './mapConfig'

const pickerIcon = L.divIcon({
  html: `<div style="background:#4f46e5;width:20px;height:20px;border-radius:50%;border:3px solid white;box-shadow:0 2px 8px rgba(0,0,0,.4)"></div>`,
  iconSize: [20, 20],
  iconAnchor: [10, 10],
  className: '',
})

function ClickHandler({ onPick, disabled }) {
  useMapEvents({
    click: (e) => {
      if (disabled) return
      onPick(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

function FlyToMarker({ pos }) {
  const map = useMap()
  useEffect(() => {
    if (pos) map.flyTo([pos.lat, pos.lng], 13, { duration: 1.2 })
  }, [pos, map])
  return null
}

function FlyToFocus({ target }) {
  const map = useMap()

  useEffect(() => {
    if (!target) return
    map.flyTo([target.lat, target.lng], target.zoom ?? 13, { duration: 1.2 })
  }, [target, map])

  return null
}

export default function MapPicker({
  lat,
  lon,
  onChange,
  focusTarget = null,
  helperText = 'Click on the map to place a pin',
  isLoading = false,
  loadingText = 'Loading map data...',
}) {
  const [pos, setPos] = useState(
    lat && lon ? { lat: Number(lat), lng: Number(lon) } : null
  )

  useEffect(() => {
    if (isLoading) {
      return
    }

    if (lat && lon) {
      setPos({ lat: Number(lat), lng: Number(lon) })
      return
    }

    setPos(null)
  }, [isLoading, lat, lon])

  const handlePick = (la, lo) => {
    const rounded = { lat: parseFloat(la.toFixed(6)), lng: parseFloat(lo.toFixed(6)) }
    setPos(rounded)
    onChange(rounded.lat, rounded.lng)
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <MapPin className="w-4 h-4 text-primary-500" />
        {helperText}
        {pos && (
          <span className="ml-auto font-mono text-xs bg-slate-100 px-2 py-0.5 rounded">
            {pos.lat}, {pos.lng}
          </span>
        )}
      </div>
      <div className="relative h-72 rounded-xl overflow-hidden border border-slate-200">
        <MapContainer
          center={pos ? [pos.lat, pos.lng] : [20, 0]}
          zoom={pos ? 12 : 2}
          className="w-full h-full"
          {...DEFAULT_MAP_PROPS}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; OpenStreetMap'
            {...DEFAULT_TILE_PROPS}
          />
          <ClickHandler onPick={handlePick} disabled={isLoading} />
          <FlyToFocus target={focusTarget} />
          <FlyToMarker pos={pos} />
          {pos && <Marker position={[pos.lat, pos.lng]} icon={pickerIcon} />}
        </MapContainer>
        {isLoading && (
          <div className="absolute inset-0 z-[500] flex flex-col items-center justify-center gap-3 bg-white/70 backdrop-blur-[1px]">
            <div className="rounded-2xl border border-slate-200 bg-white/95 px-5 py-4 shadow-lg">
              <div className="flex items-center gap-3 text-sm text-slate-700">
                <LoadingSpinner size="sm" />
                <span>{loadingText}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
