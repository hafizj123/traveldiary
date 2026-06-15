import client from './client'

export const authApi = {
  register: (data)    => client.post('/auth/register', data).then(r => r.data),
  verifyOtp: (data)   => client.post('/auth/verify-otp', data).then(r => r.data),
  resendOtp: (data)   => client.post('/auth/resend-otp', data).then(r => r.data),
  forgotPassword: (data) => client.post('/auth/forgot-password', data).then(r => r.data),
  resetPassword: (data) => client.post('/auth/reset-password', data).then(r => r.data),
  login: (data)       => client.post('/auth/login', data).then(r => r.data),
  googleLogin: (credential) => client.post('/auth/google', { credential }).then(r => r.data),
  me: (token)         => client.get('/auth/me', token ? {
    headers: { Authorization: `Bearer ${token}` },
  } : undefined).then(r => r.data),
}
