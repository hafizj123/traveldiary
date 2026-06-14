export function buildShareUrlFromSlug(shareSlug, fallbackUrl = '') {
  if (!shareSlug) return fallbackUrl || ''
  const explicitBase = String(import.meta.env.VITE_PUBLIC_APP_URL || '').trim().replace(/\/+$/, '')
  const runtimeBase = typeof window !== 'undefined' ? window.location.origin.replace(/\/+$/, '') : ''
  const base = explicitBase || runtimeBase
  if (!base) return fallbackUrl || ''
  return `${base}/shared/${shareSlug}`
}
