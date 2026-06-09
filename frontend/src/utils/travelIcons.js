import {
  Plane, Train, Car, Bus, Footprints, Ship, MoreHorizontal,
} from 'lucide-react'

export const TRAVEL_METHODS = [
  { value: 'flight', label: 'Flight',  Icon: Plane,          color: '#3B82F6', lineStyle: [8, 6] },
  { value: 'train',  label: 'Train',   Icon: Train,          color: '#EF4444', lineStyle: null },
  { value: 'car',    label: 'Car',     Icon: Car,            color: '#10B981', lineStyle: null },
  { value: 'bus',    label: 'Bus',     Icon: Bus,            color: '#F97316', lineStyle: null },
  { value: 'walk',   label: 'Walk',    Icon: Footprints,     color: '#8B5CF6', lineStyle: [4, 4] },
  { value: 'ferry',  label: 'Ferry',   Icon: Ship,           color: '#06B6D4', lineStyle: [6, 4] },
  { value: 'other',  label: 'Other',   Icon: MoreHorizontal, color: '#6B7280', lineStyle: null },
]

export function getMethod(value) {
  return TRAVEL_METHODS.find(m => m.value === value) || TRAVEL_METHODS[6]
}

export function methodColor(value) {
  return getMethod(value).color
}
