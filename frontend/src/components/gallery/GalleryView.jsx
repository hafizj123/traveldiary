import { useState } from 'react'
import { X } from 'lucide-react'
import { fmtDate } from '../../utils/formatDate'

export default function GalleryView({ points = [] }) {
  const [selected, setSelected] = useState(null)
  const withPhoto = points.filter(p => p.image_url)

  if (!withPhoto.length) {
    return (
      <div className="text-center py-16 text-slate-400">
        <p>No photos uploaded yet.</p>
      </div>
    )
  }

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        {withPhoto.map(pt => (
          <button
            key={pt.id}
            onClick={() => setSelected(pt)}
            className="relative group overflow-hidden rounded-xl aspect-square bg-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <img
              src={pt.image_url}
              alt={pt.place_name}
              className="w-full h-full object-cover transition-transform group-hover:scale-105"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end p-2">
              <div className="text-left">
                <p className="text-white text-xs font-medium truncate">{pt.place_name}</p>
                <p className="text-white/70 text-xs">{fmtDate(pt.visit_date)}</p>
              </div>
            </div>
          </button>
        ))}
      </div>

      {/* Lightbox */}
      {selected && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4" onClick={() => setSelected(null)}>
          <button className="absolute top-4 right-4 text-white p-2 hover:bg-white/10 rounded-lg">
            <X className="w-6 h-6" />
          </button>
          <div className="max-w-3xl w-full" onClick={e => e.stopPropagation()}>
            <img
              src={selected.image_url}
              alt={selected.place_name}
              className="w-full max-h-[75vh] object-contain rounded-lg"
            />
            <div className="mt-3 text-center">
              <p className="text-white font-semibold">{selected.place_name}</p>
              <p className="text-white/60 text-sm">{selected.city ? `${selected.city}, ` : ''}{selected.country} · {fmtDate(selected.visit_date)}</p>
              {selected.description && (
                <p className="text-white/80 text-sm mt-1">{selected.description}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
