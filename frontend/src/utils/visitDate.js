function resolveVisitDateBounds(trip, options = {}) {
  const minDateCandidates = [trip?.start_date, options.minDate].filter(Boolean)
  const maxDateCandidates = [trip?.end_date, options.maxDate].filter(Boolean)

  return {
    minDate: minDateCandidates.length > 0 ? minDateCandidates.reduce((latest, current) => (
      current > latest ? current : latest
    )) : '',
    maxDate: maxDateCandidates.length > 0 ? maxDateCandidates.reduce((earliest, current) => (
      current < earliest ? current : earliest
    )) : '',
  }
}

export function isVisitDateWithinTripRange(visitDate, trip, options = {}) {
  if (!visitDate || !trip) return true
  const { minDate, maxDate } = resolveVisitDateBounds(trip, options)
  if (minDate && visitDate < minDate) return false
  if (maxDate && visitDate > maxDate) return false
  return true
}


export function getVisitDateRangeError(visitDate, trip, options = {}) {
  if (!visitDate || !trip) return ''
  const { minDate, maxDate } = resolveVisitDateBounds(trip, options)
  if (minDate && visitDate < minDate) {
    return `Visit date must be on or after ${minDate}.`
  }
  if (maxDate && visitDate > maxDate) {
    return `Visit date must be on or before ${maxDate}.`
  }
  return ''
}
