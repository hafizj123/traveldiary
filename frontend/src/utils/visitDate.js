export function isVisitDateWithinTripRange(visitDate, trip) {
  if (!visitDate || !trip) return true
  if (trip.start_date && visitDate < trip.start_date) return false
  if (trip.end_date && visitDate > trip.end_date) return false
  return true
}


export function getVisitDateRangeError(visitDate, trip) {
  if (!visitDate || !trip) return ''
  if (trip.start_date && visitDate < trip.start_date) {
    return `Visit date must be on or after ${trip.start_date}.`
  }
  if (trip.end_date && visitDate > trip.end_date) {
    return `Visit date must be on or before ${trip.end_date}.`
  }
  return ''
}
