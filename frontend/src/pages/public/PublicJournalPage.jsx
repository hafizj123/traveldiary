import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Globe } from 'lucide-react'

import { publicApi } from '../../api/public'
import { useAuth } from '../../contexts/AuthContext'
import LoadingSpinner from '../../components/ui/LoadingSpinner'
import JournalRenderer from '../../components/journal/JournalRenderer'

export default function PublicJournalPage() {
  const { username, tripId, shareSlug } = useParams()
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    setError('')
    const loader = shareSlug ? publicApi.sharedTripJournal(shareSlug) : publicApi.tripJournal(username, tripId)
    loader
      .then(setData)
      .catch(() => setError('Travel journal not found'))
      .finally(() => setLoading(false))
  }, [shareSlug, username, tripId])

  if (loading) return <div className="min-h-screen flex items-center justify-center"><LoadingSpinner size="lg" /></div>

  return (
    <div className="min-h-screen journal-public-shell bg-slate-50">
      <header className="bg-white border-b border-slate-100 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex h-16 items-center justify-between">
          <Link to={user ? '/dashboard' : '/'} className="flex items-center gap-2 font-bold text-primary-600">
            <Globe className="w-5 h-5" /> Travel Diary
          </Link>
          <div className="flex items-center gap-3">
            {data?.owner ? (
              <Link to={`/u/${data.owner}`} className="text-sm text-slate-500 hover:text-primary-600">
                View {data.owner}'s trips
              </Link>
            ) : null}
            <Link to="/shared-trips" className="text-sm text-primary-600 font-medium hover:underline">Shared Trips</Link>
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        {error ? (
          <div className="py-24 text-center text-slate-400">{error}</div>
        ) : data ? (
          <div className="print-journal-page">
            <JournalRenderer trip={data.trip} journal={data.journal} ownerName={data.owner} showProviderLabel={false} />
          </div>
        ) : null}
      </div>
    </div>
  )
}
