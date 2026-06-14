import { useEffect, useRef, useState } from 'react'

const GOOGLE_SCRIPT_ID = 'google-identity-services'

function loadGoogleScript() {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) {
      resolve(window.google)
      return
    }

    const existing = document.getElementById(GOOGLE_SCRIPT_ID)
    if (existing) {
      existing.addEventListener('load', () => resolve(window.google), { once: true })
      existing.addEventListener('error', reject, { once: true })
      return
    }

    const script = document.createElement('script')
    script.id = GOOGLE_SCRIPT_ID
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.defer = true
    script.onload = () => resolve(window.google)
    script.onerror = reject
    document.head.appendChild(script)
  })
}

export default function GoogleSignInButton({ onCredential, text = 'continue_with' }) {
  const containerRef = useRef(null)
  const [error, setError] = useState('')
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID

  useEffect(() => {
    if (!clientId || !containerRef.current) return undefined

    let cancelled = false
    ;(async () => {
      try {
        const google = await loadGoogleScript()
        if (cancelled || !google?.accounts?.id || !containerRef.current) return

        google.accounts.id.initialize({
          client_id: clientId,
          callback: (response) => {
            if (response?.credential) {
              onCredential(response.credential)
            }
          },
        })
        containerRef.current.innerHTML = ''
        google.accounts.id.renderButton(containerRef.current, {
          theme: 'outline',
          size: 'large',
          shape: 'pill',
          width: 320,
          text,
        })
      } catch {
        if (!cancelled) {
          setError('Google sign-in is unavailable right now.')
        }
      }
    })()

    return () => { cancelled = true }
  }, [clientId, onCredential, text])

  if (!clientId) return null

  return (
    <div className="space-y-2">
      <div ref={containerRef} className="flex justify-center" />
      {error ? <p className="text-center text-xs text-red-500">{error}</p> : null}
    </div>
  )
}

export function isGoogleSignInAvailable() {
  return Boolean(import.meta.env.VITE_GOOGLE_CLIENT_ID)
}
