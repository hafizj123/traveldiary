import { Link } from 'react-router-dom'
import { MapPin, Calendar, Globe, Lock, Unlock } from 'lucide-react'
import { fmtDateRange } from '../../utils/formatDate'

export default function TripCard({ trip }) {
  return (
    <Link
      to={`/trips/${trip.id}`}
      className="group block bg-white rounded-xl border border-slate-100 shadow-sm hover:shadow-md transition-shadow overflow-hidden"
    >
      {/* Cover image */}
      <div className="h-40 bg-gradient-to-br from-primary-500 to-sky-500 relative overflow-hidden">
        {trip.cover_image_url ? (
          <img
            src={trip.cover_image_url}
            alt={trip.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform"
          />
        ) : (
          <div className="flex items-center justify-center h-full">
            <Globe className="w-12 h-12 text-white/40" />
          </div>
        )}
        <div className="absolute top-2 right-2">
          {trip.visibility === 'public'
            ? <span className="flex items-center gap-1 bg-green-500/90 text-white text-xs px-2 py-0.5 rounded-full"><Unlock className="w-3 h-3" />Public</span>
            : <span className="flex items-center gap-1 bg-black/40 text-white text-xs px-2 py-0.5 rounded-full"><Lock className="w-3 h-3" />Private</span>
          }
        </div>
      </div>

      <div className="p-4 space-y-1">
        <h3 className="font-semibold text-slate-800 group-hover:text-primary-600 transition-colors truncate">
          {trip.title}
        </h3>
        {(trip.start_date || trip.end_date) && (
          <p className="text-xs text-slate-400 flex items-center gap-1">
            <Calendar className="w-3 h-3" />
            {fmtDateRange(trip.start_date, trip.end_date)}
          </p>
        )}
        {trip.description && (
          <p className="text-sm text-slate-500 line-clamp-2">{trip.description}</p>
        )}
      </div>
    </Link>
  )
}
