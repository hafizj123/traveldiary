import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { fmtDate } from '../../utils/formatDate'

export default function GalleryView({ points = [] }) {
  const [selectedIndex, setSelectedIndex] = useState(null)
  const [touchStartX, setTouchStartX] = useState(null)
  const withPhoto = useMemo(() => points.filter((point) => point.image_url), [points])
  const selected = selectedIndex === null ? null : withPhoto[selectedIndex] || null

  const closeLightbox = () => {
    setSelectedIndex(null)
    setTouchStartX(null)
  }

  const showPrevious = () => {
    if (!withPhoto.length || selectedIndex === null) return
    setSelectedIndex((current) => (current - 1 + withPhoto.length) % withPhoto.length)
  }

  const showNext = () => {
    if (!withPhoto.length || selectedIndex === null) return
    setSelectedIndex((current) => (current + 1) % withPhoto.length)
  }

  useEffect(() => {
    if (selectedIndex === null) return undefined

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') closeLightbox()
      if (event.key === 'ArrowLeft') showPrevious()
      if (event.key === 'ArrowRight') showNext()
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [selectedIndex, withPhoto.length])

  useEffect(() => {
    if (selectedIndex === null) return undefined
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [selectedIndex])

  if (!withPhoto.length) {
    return (
      <div className="py-16 text-center text-slate-400">
        <p>No photos uploaded yet.</p>
      </div>
    )
  }

  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        {withPhoto.map((point, index) => (
          <button
            key={point.id}
            onClick={() => setSelectedIndex(index)}
            className="group relative aspect-square overflow-hidden rounded-xl bg-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <img
              src={point.image_url}
              alt={point.place_name}
              className="h-full w-full object-cover transition-transform group-hover:scale-105"
            />
            <div className="absolute inset-0 flex items-end bg-gradient-to-t from-black/60 to-transparent p-2 opacity-0 transition-opacity group-hover:opacity-100">
              <div className="text-left">
                <p className="truncate text-xs font-medium text-white">{point.place_name}</p>
                <p className="text-xs text-white/70">{fmtDate(point.visit_date)}</p>
              </div>
            </div>
          </button>
        ))}
      </div>

      {selected && createPortal(
        <div
          className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/90 p-4 sm:p-6"
          onClick={closeLightbox}
        >
          <button
            type="button"
            onClick={closeLightbox}
            className="absolute right-4 top-4 z-10 rounded-lg p-2 text-white hover:bg-white/10"
            aria-label="Close image viewer"
          >
            <X className="h-6 w-6" />
          </button>

          {withPhoto.length > 1 && (
            <div className="absolute left-4 top-4 z-10 rounded-full bg-black/45 px-3 py-1.5 text-xs font-medium text-white/90 backdrop-blur-sm">
              {selectedIndex + 1} / {withPhoto.length}
            </div>
          )}

          {withPhoto.length > 1 && (
            <>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation()
                  showPrevious()
                }}
                className="absolute left-3 top-1/2 z-10 hidden -translate-y-1/2 rounded-full bg-black/45 p-3 text-white backdrop-blur-sm hover:bg-black/60 sm:block"
                aria-label="Previous image"
              >
                <ChevronLeft className="h-6 w-6" />
              </button>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation()
                  showNext()
                }}
                className="absolute right-3 top-1/2 z-10 hidden -translate-y-1/2 rounded-full bg-black/45 p-3 text-white backdrop-blur-sm hover:bg-black/60 sm:block"
                aria-label="Next image"
              >
                <ChevronRight className="h-6 w-6" />
              </button>
            </>
          )}

          <div
            className="w-full max-w-5xl"
            onClick={(event) => event.stopPropagation()}
            onTouchStart={(event) => setTouchStartX(event.changedTouches[0]?.clientX ?? null)}
            onTouchEnd={(event) => {
              if (touchStartX === null || withPhoto.length <= 1) return
              const touchEndX = event.changedTouches[0]?.clientX ?? touchStartX
              const deltaX = touchEndX - touchStartX
              setTouchStartX(null)
              if (Math.abs(deltaX) < 50) return
              if (deltaX > 0) showPrevious()
              else showNext()
            }}
          >
            <div className="flex items-center justify-center gap-3 sm:hidden">
              {withPhoto.length > 1 && (
                <button
                  type="button"
                  onClick={showPrevious}
                  className="rounded-full bg-black/45 p-2.5 text-white backdrop-blur-sm hover:bg-black/60"
                  aria-label="Previous image"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
              )}
              <img
                src={selected.image_url}
                alt={selected.place_name}
                className="max-h-[68vh] min-w-0 flex-1 rounded-lg object-contain"
              />
              {withPhoto.length > 1 && (
                <button
                  type="button"
                  onClick={showNext}
                  className="rounded-full bg-black/45 p-2.5 text-white backdrop-blur-sm hover:bg-black/60"
                  aria-label="Next image"
                >
                  <ChevronRight className="h-5 w-5" />
                </button>
              )}
            </div>

            <img
              src={selected.image_url}
              alt={selected.place_name}
              className="hidden max-h-[78vh] w-full rounded-lg object-contain sm:block"
            />

            <div className="mx-auto mt-3 max-w-3xl break-words px-2 text-center">
              <p className="break-words font-semibold text-white">{selected.place_name}</p>
              <p className="break-words text-sm text-white/60">
                {selected.city ? `${selected.city}, ` : ''}
                {selected.country} · {fmtDate(selected.visit_date)}
              </p>
            </div>

            {withPhoto.length > 1 && (
              <p className="mt-2 text-center text-xs text-white/50 sm:hidden">Swipe left or right to browse</p>
            )}
          </div>
        </div>
      , document.body)}
    </>
  )
}
