import { createContext, useContext, useState, useEffect } from 'react'
import { authApi } from '../api/auth'
import { setUnauthorizedHandler } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null)
  const [loading, setLoading] = useState(true)

  // Register soft-logout handler so 401s don't cause hard page reloads
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
  }, [])

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      authApi.me()
        .then(setUser)
        .catch(() => localStorage.removeItem('token'))
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = (token, userData) => {
    localStorage.setItem('token', token)
    setUser(userData)
  }

  const logout = () => {
    localStorage.removeItem('token')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
