import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Globe } from 'lucide-react'
import { authApi } from '../../api/auth'
import { useAuth } from '../../contexts/AuthContext'
import Button from '../../components/ui/Button'
import Input  from '../../components/ui/Input'
import toast  from 'react-hot-toast'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [form, setForm]   = useState({ email: '', password: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const token = await authApi.login(form)
      localStorage.setItem('token', token.access_token)
      const me = await authApi.me()
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

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <Link to="/" className="inline-flex items-center gap-2 text-primary-600 font-bold text-xl">
            <Globe className="w-7 h-7" /> Travel Diary
          </Link>
          <h1 className="mt-4 text-2xl font-bold text-slate-800">Welcome back</h1>
          <p className="text-slate-500 text-sm">Sign in to your account</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-4">
          {error && <div className="bg-red-50 text-red-700 text-sm px-3 py-2 rounded-lg">{error}</div>}
          <Input label="Email" type="email" value={form.email} onChange={e => setForm(f => ({...f, email: e.target.value}))} required placeholder="you@example.com" />
          <Input label="Password" type="password" value={form.password} onChange={e => setForm(f => ({...f, password: e.target.value}))} required placeholder="••••••••" />
          <Button type="submit" loading={loading} className="w-full">Sign in</Button>
        </form>

        <p className="text-center text-sm text-slate-500">
          No account?{' '}
          <Link to="/register" className="text-primary-600 font-medium hover:underline">Create one</Link>
        </p>
      </div>
    </div>
  )
}
