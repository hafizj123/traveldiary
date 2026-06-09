import { useState, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { Globe, Mail } from 'lucide-react'
import { authApi } from '../../api/auth'
import Button from '../../components/ui/Button'
import Input  from '../../components/ui/Input'

export default function VerifyOTPPage() {
  const navigate  = useNavigate()
  const location  = useLocation()
  const email     = location.state?.email || ''
  const debugOtp  = location.state?.debug_otp || ''

  const [otp, setOtp]         = useState('')
  const [loading, setLoading] = useState(false)
  const [resending, setResending] = useState(false)
  const [error, setError]     = useState('')
  const [success, setSuccess] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await authApi.verifyOtp({ email, otp_code: otp })
      navigate('/login', { state: { verified: true } })
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid OTP')
    } finally {
      setLoading(false)
    }
  }

  const handleResend = async () => {
    setResending(true)
    setError('')
    try {
      const res = await authApi.resendOtp({ email })
      setSuccess('OTP resent!')
      if (res.debug_otp) alert(`DEBUG OTP: ${res.debug_otp}`)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to resend')
    } finally {
      setResending(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <Link to="/" className="inline-flex items-center gap-2 text-primary-600 font-bold text-xl">
            <Globe className="w-7 h-7" /> Travel Diary
          </Link>
          <div className="mt-4 w-12 h-12 bg-primary-50 rounded-full flex items-center justify-center mx-auto">
            <Mail className="w-6 h-6 text-primary-600" />
          </div>
          <h1 className="mt-3 text-2xl font-bold text-slate-800">Verify your email</h1>
          <p className="text-slate-500 text-sm mt-1">
            We sent a 6-digit code to <strong>{email}</strong>
          </p>
          {debugOtp && (
            <div className="mt-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-sm text-amber-800">
              <strong>Dev mode OTP:</strong> {debugOtp}
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-4">
          {error   && <div className="bg-red-50 text-red-700 text-sm px-3 py-2 rounded-lg">{error}</div>}
          {success && <div className="bg-green-50 text-green-700 text-sm px-3 py-2 rounded-lg">{success}</div>}
          <Input
            label="Verification code"
            value={otp}
            onChange={e => setOtp(e.target.value)}
            required
            maxLength={6}
            placeholder="123456"
            className="text-center text-lg tracking-widest font-mono"
          />
          <Button type="submit" loading={loading} className="w-full">Verify email</Button>
        </form>

        <div className="text-center space-y-2">
          <button onClick={handleResend} disabled={resending} className="text-sm text-primary-600 hover:underline disabled:opacity-50">
            {resending ? 'Resending…' : 'Resend code'}
          </button>
          <p className="text-sm text-slate-400">
            Wrong email? <Link to="/register" className="text-primary-600 hover:underline">Register again</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
