export function validateTripForm(form) {
  const errors = {}
  const title = (form.title || '').trim()
  const startDate = (form.start_date || '').trim()
  const endDate = (form.end_date || '').trim()
  const startingPlaceName = (form.starting_place_name || '').trim()
  const startingCountry = (form.starting_country || '').trim()
  const plannedCountries = Array.isArray(form.planned_countries) ? form.planned_countries : []

  if (!title) {
    errors.title = 'Trip title is required'
  }

  if (!startDate) {
    errors.start_date = 'Start date is required'
  }

  if (!endDate) {
    errors.end_date = 'End date is required'
  }

  if (startDate && endDate && endDate < startDate) {
    errors.end_date = 'End date must be on or after start date'
  }

  if (!startingPlaceName) {
    errors.starting_place_name = 'Starting place is required'
  }

  if (!startingCountry) {
    errors.starting_country = 'Starting country is required'
  }

  if (form.starting_latitude === '' || form.starting_latitude === null || form.starting_latitude === undefined
    || form.starting_longitude === '' || form.starting_longitude === null || form.starting_longitude === undefined) {
    errors.starting_place_name = errors.starting_place_name || 'Pick a starting place from search'
  }

  if (plannedCountries.length === 0) {
    errors.planned_countries = 'Select at least one country for this trip'
  }

  return {
    errors,
    sanitized: {
      ...form,
      title,
      start_date: startDate,
      end_date: endDate,
      starting_place_name: startingPlaceName,
      starting_country: startingCountry,
      starting_city: (form.starting_city || '').trim(),
      planned_countries: plannedCountries,
    },
  }
}
