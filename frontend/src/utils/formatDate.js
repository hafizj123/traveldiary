import { format, parseISO } from 'date-fns'

export function fmtDate(dateStr) {
  if (!dateStr) return ''
  try {
    const d = typeof dateStr === 'string' ? parseISO(dateStr) : dateStr
    return format(d, 'dd MMM yyyy')
  } catch {
    return dateStr
  }
}

export function fmtDateRange(start, end) {
  if (!start) return ''
  if (!end)   return fmtDate(start)
  return `${fmtDate(start)} – ${fmtDate(end)}`
}
