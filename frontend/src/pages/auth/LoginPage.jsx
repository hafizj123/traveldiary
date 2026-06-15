import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { Globe } from 'lucide-react'
import toast from 'react-hot-toast'

import { authApi } from '../../api/auth'
import { useAuth } from '../../contexts/AuthContext'
import Button from '../../components/ui/Button'
import GoogleSignInButton, { isGoogleSignInAvailable } from '../../components/ui/GoogleSignInButton'
import Input from '../../components/ui/Input'
import heroImage from '../../image/pexels-marina-zasorina-7634437.jpg'

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login } = useAuth()
  const googleAvailable = isGoogleSignInAvailable()
  const [form, setForm] = useState({ email: location.state?.email || '', password: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(location.state?.resetSuccess || '')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setNotice('')
    setLoading(true)
    try {
      const token = await authApi.login(form)
      const me = await authApi.me(token.access_token)
      login(token.access_token, me)
      navigate('/dashboard')
    } catch (err) {
      const msg = err.response?.data?.detail || 'Login failed'
      if (msg.includes('verify')) {
        setError(msg)
        navigate('/verify-otp', { state: { email: form.email } })
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleLogin = async (credential) => {
    setError('')
    setNotice('')
    setLoading(true)
    try {
      const token = await authApi.googleLogin(credential)
      const me = await authApi.me(token.access_token)
      login(token.access_token, me)
      toast.success('Signed in with Google')
      navigate('/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || 'Google login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950">
      <div className="grid min-h-screen lg:grid-cols-[1.15fr_0.85fr]">
        <section
          className="relative hidden overflow-hidden lg:flex"
          style={{ backgroundImage: `url(${heroImage})`, backgroundSize: 'cover', backgroundPosition: 'center' }}
        >
          <div className="absolute inset-0 bg-gradient-to-br from-slate-950/70 via-slate-900/45 to-primary-900/70" />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.18),transparent_38%),radial-gradient(circle_at_bottom_right,rgba(59,130,246,0.22),transparent_34%)]" />
          <div className="relative flex min-h-screen w-full items-center">
            <div className="max-w-2xl px-10 py-16 text-white xl:px-14">
              <Link to="/" className="inline-flex items-center gap-3 text-xl font-bold text-white/95">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/14 backdrop-blur-sm">
                  <Globe className="h-6 w-6" />
                </span>
                Travel Diary
              </Link>
              <div className="mt-10 max-w-xl space-y-5">
                <p className="text-sm font-medium text-white/72">
                  Your personal travel timeline + world map diary
                </p>
                <h1 className="text-5xl font-bold leading-[1.05] text-balance">
                  Pin your memories on a
                  <br />
                  world map
                </h1>
                <p className="max-w-lg text-base leading-7 text-white/78">
                  Create visual travel timelines, track routes between places, upload photos, and share your journeys with the world.
                </p>
                <div className="flex flex-wrap gap-3 pt-3">
                  <Link to="/shared-trips" className="rounded-full border border-white/28 bg-white/10 px-5 py-3 text-sm font-semibold text-white backdrop-blur-sm transition hover:bg-white/18">
                    Explore shared trips
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10 sm:px-6 lg:px-10">
          <div className="w-full max-w-md space-y-6">
            <div className="text-center lg:text-left">
              <Link to="/" className="inline-flex items-center gap-2 text-xl font-bold text-primary-600 lg:hidden">
                <Globe className="w-7 h-7" /> Travel Diary
              </Link>
              <h1 className="mt-4 text-3xl font-bold text-slate-900">Welcome back</h1>
              <p className="mt-2 text-sm text-slate-500">Sign in to continue building your travel diary.</p>
            </div>

            <form onSubmit={handleSubmit} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/60 sm:p-8">
              <div className="space-y-4">
                {notice ? <div className="rounded-2xl bg-green-50 px-4 py-3 text-sm text-green-700">{notice}</div> : null}
                {error ? <div className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}
                <Input
                  label="Email"
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                  required
                  placeholder="you@example.com"
                />
                <Input
                  label="Password"
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                  required
                  placeholder="Password"
                />
                <div className="flex justify-end">
                  <Link to="/forgot-password" className="text-sm font-medium text-primary-600 hover:underline">
                    Forgot password?
                  </Link>
                </div>
                <Button type="submit" loading={loading} className="w-full">
                  Sign in
                </Button>
              </div>

              {googleAvailable ? (
                <div className="mt-5">
                  <div className="flex items-center gap-3 py-1">
                    <div className="h-px flex-1 bg-slate-200" />
                    <span className="text-xs uppercase tracking-wide text-slate-400">or</span>
                    <div className="h-px flex-1 bg-slate-200" />
                  </div>
                  <div className="mt-4">
                    <GoogleSignInButton onCredential={handleGoogleLogin} />
                  </div>
                </div>
              ) : null}

              <p className="mt-6 text-center text-sm text-slate-500">
                No account?{' '}
                <Link to="/register" className="font-medium text-primary-600 hover:underline">Create one</Link>
              </p>
            </form>

            <div className="rounded-3xl bg-white/70 p-5 text-sm text-slate-600 shadow-sm ring-1 ring-slate-200/70 backdrop-blur lg:hidden">
              <p className="font-semibold text-slate-800">Your personal travel timeline + world map diary</p>
              <p className="mt-2 leading-6">
                Create visual travel timelines, track routes between places, upload photos, and share your journeys with the world.
              </p>
              <div className="mt-4 flex flex-wrap gap-3">
                <Link to="/register" className="font-semibold text-primary-600 hover:underline">Start for free</Link>
                <Link to="/shared-trips" className="font-semibold text-primary-600 hover:underline">Explore shared trips</Link>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
