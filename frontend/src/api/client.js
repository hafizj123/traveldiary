import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
})

// AuthContext registers this so 401s trigger a soft React logout instead of a hard reload
let _onUnauthorized = null
export function setUnauthorizedHandler(fn) { _onUnauthorized = fn }

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      if (_onUnauthorized) _onUnauthorized()
    }
    return Promise.reject(err)
  }
)

export default client
