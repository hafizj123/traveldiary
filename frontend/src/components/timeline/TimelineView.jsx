import { Link } from 'react-router-dom'
import { Edit2, Trash2 } from 'lucide-react'
import { fmtDate } from '../../utils/formatDate'
import { getMethod } from '../../utils/travelIcons'

export default function TimelineView({ points = [], segments = [], tripId, onDelete }) {
  if (!points.length) {
    return (
      <div className="text-center py-16 text-slate-400">
        <p>No locations added yet.</p>
      </div>
    )
  }

  // Build segment lookup by to_point_id
  const segByTo = {}
  segments.forEach(s => { segByTo[s.to_point_id] = s })

  return (
    <div className="space-y-0">
      {points.map((pt, i) => {
        const seg    = segByTo[pt.id]
        const method = seg ? getMethod(seg.travel_method) : null
        const Icon   = method?.Icon

        return (
          <div key={pt.id}>
            {/* Transport connector — shown above every point except the first */}
            {method && (
              <div className="flex items-stretch gap-0 pl-6 py-0">
                {/* Left column: line + badge column */}
                <div className="flex flex-col items-center" style={{ width: '1.25rem' }}>
                  {/* line segment above badge */}
                  <div className="w-0.5 bg-slate-200 flex-1" style={{ minHeight: '1rem' }} />
                  {/* colored dot on the line for the connector */}
                  <div
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ background: method.color }}
                  />
                  {/* line segment below badge */}
                  <div className="w-0.5 bg-slate-200 flex-1" style={{ minHeight: '1rem' }} />
                </div>

                {/* Badge */}
                <div className="flex items-center pl-4 py-1">
                  <span
                    className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full"
                    style={{ color: method.color, background: `${method.color}18` }}
                  >
                    <Icon className="w-3 h-3" />
                    {method.label}
                  </span>
                </div>
              </div>
            )}

            {/* Point row */}
            <div className="flex items-stretch gap-0 pl-6">
              {/* Left column: dot + line */}
              <div className="flex flex-col items-center" style={{ width: '1.25rem' }}>
                {/* Line above dot (only if not first point) */}
                {i > 0 && !method && (
                  <div className="w-0.5 bg-slate-200" style={{ height: '1.25rem' }} />
                )}
                {/* The dot */}
                <div className="w-3 h-3 rounded-full bg-primary-600 border-2 border-white shadow-sm flex-shrink-0 mt-3.5" />
                {/* Line below dot (if not last point) */}
                {i < points.length - 1 && (
                  <div className="w-0.5 bg-slate-200 flex-1" />
                )}
              </div>

              {/* Card */}
              <div className="flex-1 pl-5 pb-0 pt-2" style={{ paddingBottom: i < points.length - 1 ? '0' : '0' }}>
                <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden mb-2">
                  {pt.image_url && (
                    <img
                      src={pt.image_url}
                      alt={pt.place_name}
                      className="w-full h-48 object-cover"
                    />
                  )}
                  <div className="p-4 space-y-1">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="font-semibold text-slate-800">{pt.place_name}</h3>
                        <p className="text-sm text-slate-500">{pt.city ? `${pt.city}, ` : ''}{pt.country}</p>
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <span className="text-xs text-slate-400 whitespace-nowrap">{fmtDate(pt.visit_date)}</span>
                        {tripId && (
                          <Link
                            to={`/trips/${tripId}/points/${pt.id}/edit?returnTo=timeline`}
                            className="ml-2 p-1.5 rounded-lg text-slate-400 hover:text-primary-600 hover:bg-primary-50 transition-colors"
                            title="Edit"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </Link>
                        )}
                        {onDelete && (
                          <button
                            onClick={() => onDelete(pt.id)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                            title="Delete"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>

                    {pt.weather_data && (
                      <div className="flex items-center gap-1 text-xs text-slate-500">
                        <img
                          src={`https://openweathermap.org/img/wn/${pt.weather_data.icon}.png`}
                          alt=""
                          className="w-5 h-5"
                        />
                        {pt.weather_data.temp_max != null
                          ? `${pt.weather_data.temp_min}–${pt.weather_data.temp_max}°C`
                          : `${Math.round(pt.weather_data.temp || 0)}°C`}
                        {' · '}{pt.weather_data.description}
                        {pt.weather_data.precipitation != null && ` · ${pt.weather_data.precipitation}mm rain`}
                      </div>
                    )}

                    {pt.description && (
                      <p className="text-sm text-slate-600 mt-2 leading-relaxed">{pt.description}</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
