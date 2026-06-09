import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Globe } from 'lucide-react'
import { authApi } from '../../api/auth'
import Button from '../../components/ui/Button'
import Input  from '../../components/ui/Input'

export default function RegisterPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '', username: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await authApi.register({
        email: form.email,
        password: form.password,
        username: form.username || undefined,
      })
      navigate('/verify-otp', { state: { email: form.email, debug_otp: res.debug_otp } })
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed')
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
          <h1 className="mt-4 text-2xl font-bold text-slate-800">Create your account</h1>
          <p className="text-slate-500 text-sm">Start mapping your adventures</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-4">
          {error && <div className="bg-red-50 text-red-700 text-sm px-3 py-2 rounded-lg">{error}</div>}
          <Input label="Email" type="email" value={form.email} onChange={set('email')} required placeholder="you@example.com" />
          <Input label="Username (optional)" value={form.username} onChange={set('username')} placeholder="hafiz" />
          <div>
            <Input label="Password" type="password" value={form.password} onChange={set('password')} required placeholder="Min. 8 characters" />
            <p className="text-xs text-slate-400 mt-1">Minimum 8 characters</p>
          </div>
          <Button type="submit" loading={loading} className="w-full">Create account</Button>
        </form>

        <p className="text-center text-sm text-slate-500">
          Already have an account?{' '}
          <Link to="/login" className="text-primary-600 font-medium hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
