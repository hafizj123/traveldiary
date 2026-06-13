import { BusFront, CableCar, MapPin, Plane, Ship, TrainFront } from 'lucide-react'

function normalize(value) {
  return String(value || '').trim().toLowerCase()
}

export function getLocationResultKind(result, preferredKind = '') {
  // Explicit transport_mode wins first (set by local DB results)
  const transportMode = normalize(result?.transport_mode)
  if (transportMode && transportMode !== 'location') {
    if (transportMode === 'flight' || transportMode === 'airport') return 'airport'
    return transportMode
  }

  // result_kind from OSM-tag classification (set by mappers in locationSearch.js)
  const resultKind = normalize(result?.result_kind)
  if (resultKind && resultKind !== 'location') {
    if (resultKind === 'flight' || resultKind === 'airport') return 'airport'
    return resultKind
  }

  // Text / tag-based fallback for results with no specific kind
  const source = normalize(result?.source)
  const placeName = normalize(result?.place_name || result?.label)
  const subtitle = normalize(result?.subtitle)
  const railwayType = normalize(result?.railway_type)
  const resultType = normalize(result?.result_type || result?.addresstype)

  if (source.includes('train')) return 'train'
  if (source.includes('bus')) return 'bus'
  if (source.includes('ferry')) return 'ferry'
  if (source.includes('airport')) return 'airport'
  if (railwayType || resultType === 'station' || subtitle.includes('train') || subtitle.includes('rail')) return 'train'
  if (subtitle.includes('bus') || placeName.includes('bus station') || resultType === 'bus_stop') return 'bus'
  if (subtitle.includes('ferry') || placeName.includes('ferry') || resultType === 'ferry_terminal') return 'ferry'
  if (resultType === 'airport' || resultType === 'aerodrome' || subtitle.includes('airport') || placeName.includes('airport')) return 'airport'
  const preferred = normalize(preferredKind)
  if (preferred && preferred !== 'other' && preferred !== 'location') {
    if (preferred === 'flight') return 'airport'
    return preferred
  }

  return 'location'
}

export function getLocationResultIcon(kind) {
  switch (normalize(kind)) {
    case 'train':
      return TrainFront
    case 'bus':
      return BusFront
    case 'ferry':
      return Ship
    case 'excursion':
    case 'lift':
    case 'gondola':
      return CableCar
    case 'airport':
    case 'flight':
      return Plane
    default:
      return MapPin
  }
}
