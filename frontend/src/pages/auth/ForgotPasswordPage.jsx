import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Globe, KeyRound, Mail } from 'lucide-react'
import toast from 'react-hot-toast'

import { authApi } from '../../api/auth'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'

export default function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState('request')
  const [email, setEmail] = useState('')
  const [otp, setOtp] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [debugOtp, setDebugOtp] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const handleRequestReset = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    setSuccess('')
    try {
      const res = await authApi.forgotPassword({ email })
      setDebugOtp(res.debug_otp || '')
      setSuccess(res.message || 'If an eligible local account exists for this email, a reset code has been sent.')
      setStep('reset')
      toast.success('If the account is eligible, a reset code has been sent')
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not send reset code')
    } finally {
      setLoading(false)
    }
  }

  const handleResetPassword = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    setSuccess('')
    try {
      const res = await authApi.resetPassword({
        email,
        otp_code: otp,
        new_password: newPassword,
      })
      toast.success('Password reset successful')
      navigate('/login', {
        state: {
          resetSuccess: res.message || 'Password reset successful. You can now sign in.',
          email,
        },
      })
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not reset password')
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
          <div className="mt-4 w-12 h-12 bg-primary-50 rounded-full flex items-center justify-center mx-auto">
            {step === 'request' ? <Mail className="w-6 h-6 text-primary-600" /> : <KeyRound className="w-6 h-6 text-primary-600" />}
          </div>
          <h1 className="mt-3 text-2xl font-bold text-slate-800">
            {step === 'request' ? 'Forgot your password?' : 'Reset your password'}
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            {step === 'request'
              ? 'Enter the email for your local account and we will send you a reset code.'
              : `Enter the 6-digit code sent to ${email} and choose a new password.`}
          </p>
          {debugOtp ? (
            <div className="mt-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-sm text-amber-800">
              <strong>Dev mode reset code:</strong> {debugOtp}
            </div>
          ) : null}
        </div>

        <form
          onSubmit={step === 'request' ? handleRequestReset : handleResetPassword}
          className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-4"
        >
          {error ? <div className="bg-red-50 text-red-700 text-sm px-3 py-2 rounded-lg">{error}</div> : null}
          {success ? <div className="bg-green-50 text-green-700 text-sm px-3 py-2 rounded-lg">{success}</div> : null}

          <Input
            label="Email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            placeholder="you@example.com"
            disabled={loading || step === 'reset'}
          />

          {step === 'reset' ? (
            <>
              <Input
                label="Reset code"
                value={otp}
                onChange={(event) => setOtp(event.target.value)}
                required
                maxLength={6}
                placeholder="123456"
                className="text-center text-lg tracking-widest font-mono"
              />
              <div>
                <Input
                  label="New password"
                  type="password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  required
                  minLength={8}
                  placeholder="Min. 8 characters"
                />
                <p className="text-xs text-slate-400 mt-1">Minimum 8 characters</p>
              </div>
            </>
          ) : null}

          <Button type="submit" loading={loading} className="w-full">
            {step === 'request' ? 'Send reset code' : 'Reset password'}
          </Button>

          {step === 'reset' ? (
            <button
              type="button"
              onClick={() => {
                setStep('request')
                setOtp('')
                setNewPassword('')
                setDebugOtp('')
                setSuccess('')
                setError('')
              }}
              className="w-full text-sm text-slate-500 hover:text-primary-600"
            >
              Use a different email
            </button>
          ) : null}
        </form>

        <p className="text-center text-sm text-slate-500">
          Back to{' '}
          <Link to="/login" className="text-primary-600 font-medium hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
