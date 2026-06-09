import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import LoadingSpinner from '../ui/LoadingSpinner'

export default function ProtectedRoute() {
  const { user, loading } = useAuth()
  if (loading) return <div className="h-screen flex items-center justify-center"><LoadingSpinner size="lg" /></div>
  if (!user)   return <Navigate to="/login" replace />
  return <Outlet />
}
