import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Globe, MapPin, Lock } from 'lucide-react'
import { publicApi } from '../../api/public'
import TripCard from '../../components/trips/TripCard'
import LoadingSpinner from '../../components/ui/LoadingSpinner'

export default function PublicProfilePage() {
  const { username } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    publicApi.profile(username)
      .then(setData)
      .catch(() => setError('User not found or has no public trips'))
      .finally(() => setLoading(false))
  }, [username])

  if (loading) return <div className="min-h-screen flex items-center justify-center"><LoadingSpinner size="lg" /></div>

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-100 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex h-16 items-center justify-between">
          <Link to="/" className="flex items-center gap-2 font-bold text-primary-600">
            <Globe className="w-5 h-5" /> Travel Diary
          </Link>
          <Link to="/login" className="text-sm text-primary-600 font-medium hover:underline">Sign in</Link>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
        {error ? (
          <div className="text-center py-24">
            <Lock className="w-12 h-12 text-slate-200 mx-auto mb-4" />
            <p className="text-slate-400">{error}</p>
          </div>
        ) : (
          <>
            <div className="text-center space-y-2">
              <div className="w-16 h-16 bg-primary-100 rounded-full flex items-center justify-center mx-auto">
                <span className="text-2xl font-bold text-primary-600">{username[0]?.toUpperCase()}</span>
              </div>
              <h1 className="text-2xl font-bold text-slate-800">{username}'s Travel Diary</h1>
              <p className="text-slate-400 text-sm">{data?.trips?.length || 0} public trips</p>
            </div>

            {data?.trips?.length === 0 ? (
              <div className="text-center py-12 text-slate-400">No public trips yet.</div>
            ) : (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {data.trips.map(t => (
                  <Link key={t.id} to={`/u/${username}/trips/${t.id}`}>
                    <TripCard trip={t} />
                  </Link>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
