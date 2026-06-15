export function buildShareUrlFromSlug(shareSlug, fallbackUrl = '') {
  if (!shareSlug) return fallbackUrl || ''
  const explicitBase = String(import.meta.env.VITE_PUBLIC_APP_URL || '').trim().replace(/\/+$/, '')
  const runtimeBase = typeof window !== 'undefined' ? window.location.origin.replace(/\/+$/, '') : ''
  const base = explicitBase || runtimeBase
  if (!base) return fallbackUrl || ''
  return `${base}/shared/${shareSlug}`
}

export async function copyTextToClipboard(text) {
  const value = String(text || '')
  if (!value) {
    throw new Error('Nothing to copy')
  }

  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value)
      return true
    } catch {
      // Fall back to a manual copy path below.
    }
  }

  if (typeof document === 'undefined') {
    throw new Error('Clipboard is unavailable')
  }

  const textArea = document.createElement('textarea')
  textArea.value = value
  textArea.setAttribute('readonly', '')
  textArea.style.position = 'fixed'
  textArea.style.top = '-9999px'
  textArea.style.left = '-9999px'
  document.body.appendChild(textArea)
  textArea.focus()
  textArea.select()
  textArea.setSelectionRange(0, textArea.value.length)

  try {
    const successful = document.execCommand('copy')
    if (!successful) {
      throw new Error('Copy command failed')
    }
    return true
  } finally {
    document.body.removeChild(textArea)
  }
}
