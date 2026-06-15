import { useEffect, useState } from 'react'
import { CalendarDays, Camera, MapPinned, Quote, Route, Users } from 'lucide-react'

import { fmtDateRange } from '../../utils/formatDate'

function formatVisitDate(value) {
  if (!value) return ''
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function useImageTextTone(imageUrl, sampleRegion = null) {
  const [tone, setTone] = useState('light')

  useEffect(() => {
    if (!imageUrl || typeof window === 'undefined') {
      setTone('light')
      return undefined
    }

    let active = true
    const image = new window.Image()
    image.crossOrigin = 'anonymous'
    image.decoding = 'async'

    image.onload = () => {
      if (!active) return

      try {
        const canvas = document.createElement('canvas')
        const context = canvas.getContext('2d', { willReadFrequently: true })
        if (!context) {
          setTone('light')
          return
        }

        const sampleSize = 24
        canvas.width = sampleSize
        canvas.height = sampleSize

        const sourceX = Math.max(0, Math.floor((sampleRegion?.x ?? 0) * image.naturalWidth))
        const sourceY = Math.max(0, Math.floor((sampleRegion?.y ?? 0) * image.naturalHeight))
        const sourceWidth = Math.max(1, Math.floor((sampleRegion?.width ?? 1) * image.naturalWidth))
        const sourceHeight = Math.max(1, Math.floor((sampleRegion?.height ?? 1) * image.naturalHeight))

        context.drawImage(
          image,
          sourceX,
          sourceY,
          Math.min(sourceWidth, image.naturalWidth - sourceX),
          Math.min(sourceHeight, image.naturalHeight - sourceY),
          0,
          0,
          sampleSize,
          sampleSize
        )

        const { data } = context.getImageData(0, 0, sampleSize, sampleSize)
        let luminanceTotal = 0
        let pixelCount = 0

        for (let index = 0; index < data.length; index += 4) {
          const alpha = data[index + 3]
          if (alpha === 0) continue

          const red = data[index]
          const green = data[index + 1]
          const blue = data[index + 2]
          luminanceTotal += (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
          pixelCount += 1
        }

        if (!pixelCount) {
          setTone('light')
          return
        }

        const averageLuminance = luminanceTotal / pixelCount
        setTone(averageLuminance > 160 ? 'dark' : 'light')
      } catch {
        setTone('light')
      }
    }

    image.onerror = () => {
      if (active) setTone('light')
    }

    image.src = imageUrl

    return () => {
      active = false
    }
  }, [imageUrl, sampleRegion?.height, sampleRegion?.width, sampleRegion?.x, sampleRegion?.y])

  return tone
}

function overlayToneClasses(tone) {
  const darkText = tone === 'dark'

  return {
    overlay: darkText ? 'journal-image-overlay-dark' : 'journal-image-overlay-light',
    pill: darkText ? 'journal-pill journal-pill-light' : 'journal-pill',
    providerPill: darkText ? 'journal-provider-pill journal-provider-pill-light' : 'journal-provider-pill',
    eyebrow: darkText ? 'text-slate-800/75' : 'text-white/70',
    title: darkText ? 'text-slate-950' : 'text-white',
    meta: darkText ? 'text-slate-800/80' : 'text-white/82',
  }
}

function buildMemoryCaption(chapter) {
  const firstLocation = chapter?.locations?.find((location) => location?.place_name)?.place_name?.trim()
  if (firstLocation) return firstLocation

  const heading = chapter?.heading?.trim()
  if (heading) return heading

  const visitDate = formatVisitDate(chapter?.visit_date)
  if (visitDate) return visitDate

  return 'Photo archive'
}

function uniqueImagesFromChapters(chapters) {
  const seen = new Set()

  return chapters.flatMap((chapter) => (
    (chapter.image_urls || []).flatMap((imageUrl) => {
      if (!imageUrl || seen.has(imageUrl)) return []
      seen.add(imageUrl)
      return [{
        url: imageUrl,
        caption: buildMemoryCaption(chapter),
      }]
    })
  ))
}

function JournalInput({ editable, value, onChange, className, multiline = false, rows = 4 }) {
  if (!editable) {
    return multiline ? <p className={className}>{value}</p> : <h2 className={className}>{value}</h2>
  }

  if (multiline) {
    return (
      <textarea
        value={value || ''}
        onChange={(event) => onChange(event.target.value)}
        rows={rows}
        className={`${className} w-full resize-y rounded-[1.35rem] border border-[#e7dccb] bg-white/90 px-4 py-3 outline-none focus:border-primary-400 focus:ring-2 focus:ring-primary-100`}
      />
    )
  }

  return (
    <input
      value={value || ''}
      onChange={(event) => onChange(event.target.value)}
      className={`${className} w-full bg-transparent outline-none`}
    />
  )
}

function MemoryGallery({ images, totalPhotos, templateKey }) {
  if (!images.length) return null

  return (
    <section className={`journal-memory-panel journal-memory-panel-${templateKey}`}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="journal-section-eyebrow">Captured moments</p>
          <h2 className="journal-section-title">A visual thread from the journey</h2>
        </div>
        <div className="rounded-full border border-white/60 bg-white/75 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
          {totalPhotos} photo{totalPhotos === 1 ? '' : 's'}
        </div>
      </div>
      <div className={`journal-memory-grid journal-memory-grid-${Math.min(images.length, 8)}`}>
        {images.map((image, index) => (
          <figure key={`${image.url}-${index}`} className="journal-memory-card">
            <img src={image.url} alt={`Trip memory ${index + 1}`} className="journal-memory-image" />
            <figcaption className="journal-memory-caption">
              <span>Memory {String(index + 1).padStart(2, '0')}</span>
              <span>{image.caption}</span>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  )
}

function FactGrid({ factCards, templateKey }) {
  return (
    <div className={`journal-fact-grid journal-fact-grid-${templateKey}`}>
      {factCards.map(({ icon: Icon, label, value }) => (
        <div key={label} className="journal-fact-card">
          <div className="journal-fact-icon">
            <Icon className="h-4 w-4" />
          </div>
          <div>
            <p className="journal-fact-label">{label}</p>
            <p className="journal-fact-value">{value}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

function EditorialChapterMedia({ chapter, index, editable, updateChapter }) {
  const imageUrl = chapter.image_urls?.[0]
  const tone = useImageTextTone(imageUrl, { x: 0.04, y: 0.52, width: 0.62, height: 0.42 })
  const contrast = overlayToneClasses(tone)

  return (
    <div className={`journal-chapter-media ${index % 2 === 1 ? 'lg:order-2' : ''}`}>
      {imageUrl ? <img src={imageUrl} alt={chapter.heading} className="journal-chapter-image" /> : <div className="journal-chapter-fallback" />}
      <div className={`journal-chapter-media-overlay ${contrast.overlay}`} />
      <div className="journal-chapter-media-content">
        <div className="journal-pill-subtle">Chapter {String(chapter.chapter_index || index + 1).padStart(2, '0')}</div>
        <JournalInput
          editable={editable}
          value={chapter.heading || ''}
          onChange={(value) => updateChapter(index, { heading: value })}
          className={`mt-4 font-serif text-3xl font-semibold leading-tight ${contrast.title}`}
        />
        <p className="mt-3 text-sm text-white/82">{formatVisitDate(chapter.visit_date)}</p>
      </div>
    </div>
  )
}

function EditorialTemplate({
  trip,
  journal,
  chapters,
  factCards,
  dateRangeLabel,
  galleryImages,
  totalPhotos,
  ownerName,
  editable,
  updateField,
  updateChapter,
  showProviderLabel,
}) {
  const coverImage = journal?.content_json?.cover_image_url || trip?.cover_image_url
  const heroTone = useImageTextTone(coverImage)
  const heroContrast = overlayToneClasses(heroTone)

  return (
    <article className="journal-screen-book journal-shell journal-template-editorial">
      <section className="journal-hero journal-hero-editorial">
        {coverImage ? <img src={coverImage} alt={journal.title} className="journal-hero-image" /> : null}
        <div className={`journal-hero-overlay ${heroContrast.overlay}`} />
        <div className="journal-hero-content">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className={heroContrast.pill}>Travel Journal</div>
            {showProviderLabel ? <div className={heroContrast.providerPill}>{journal?.content_json?.provider_label || 'Story draft'}</div> : null}
          </div>
          <div className="max-w-4xl">
            <p className={`journal-section-eyebrow ${heroContrast.eyebrow}`}>Your personal travel timeline and world map diary</p>
            <JournalInput
              editable={editable}
              value={journal.title}
              onChange={(value) => updateField('title', value)}
              className={`mt-4 font-serif text-4xl font-semibold leading-tight sm:text-5xl lg:text-6xl ${heroContrast.title}`}
            />
            <p className={`mt-5 max-w-2xl text-[15px] leading-7 ${heroContrast.meta}`}>
              {dateRangeLabel}
              {ownerName ? ` / by ${ownerName}` : ''}
            </p>
          </div>
          <FactGrid factCards={factCards} templateKey="editorial" />
        </div>
      </section>

      <div className="journal-paper px-6 py-8 sm:px-8 lg:px-10 lg:py-10">
        <section className="grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(18rem,0.9fr)]">
          <div className="journal-note-card">
            <p className="journal-section-eyebrow">Opening note</p>
            <JournalInput
              editable={editable}
              value={journal.intro_text || ''}
              onChange={(value) => updateField('intro_text', value)}
              className="mt-4 font-serif text-[18px] leading-9 text-slate-700 whitespace-pre-line"
              multiline
              rows={7}
            />
          </div>
          <div className="space-y-4">
            {trip?.travel_companions ? (
              <div className="journal-side-card">
                <div className="journal-fact-icon"><Users className="h-4 w-4" /></div>
                <div>
                  <p className="journal-fact-label">Travel companions</p>
                  <p className="mt-2 text-[15px] leading-7 text-slate-700">{trip.travel_companions}</p>
                </div>
              </div>
            ) : null}
            <div className="journal-side-stack">
              {factCards.slice(0, 2).map(({ icon: Icon, label, value }) => (
                <div key={label} className="journal-side-card">
                  <div className="journal-fact-icon"><Icon className="h-4 w-4" /></div>
                  <div>
                    <p className="journal-fact-label">{label}</p>
                    <p className="journal-fact-value mt-2">{value}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <MemoryGallery images={galleryImages} totalPhotos={totalPhotos} templateKey="editorial" />

        <div className="journal-divider"><span>Chapters from the route</span></div>

        <div className="space-y-8">
          {chapters.map((chapter, index) => (
            <section key={`${chapter.visit_date}-${index}`} className="journal-chapter-card journal-chapter-editorial">
              <EditorialChapterMedia chapter={chapter} index={index} editable={editable} updateChapter={updateChapter} />
              <div className={`p-6 sm:p-7 ${index % 2 === 1 ? 'lg:order-1' : ''}`}>
                <div className="journal-quote-card">
                  <div className="journal-fact-icon"><Quote className="h-4 w-4" /></div>
                  <JournalInput
                    editable={editable}
                    value={chapter.body_text || ''}
                    onChange={(value) => updateChapter(index, { body_text: value })}
                    className="font-serif text-[17px] leading-8 text-slate-700 whitespace-pre-line"
                    multiline
                    rows={8}
                  />
                </div>
                {chapter.locations?.length ? (
                  <div className="mt-5 flex flex-wrap gap-2">
                    {chapter.locations.map((location) => (
                      <span key={location.point_id} className="journal-location-chip">{location.place_name}</span>
                    ))}
                  </div>
                ) : null}
              </div>
            </section>
          ))}
        </div>

        <section className="journal-closing-card mt-10">
          <p className="journal-section-eyebrow">Closing reflection</p>
          <JournalInput
            editable={editable}
            value={journal.closing_text || ''}
            onChange={(value) => updateField('closing_text', value)}
            className="mt-4 font-serif text-[18px] leading-9 text-slate-700 whitespace-pre-line"
            multiline
            rows={5}
          />
        </section>
      </div>
    </article>
  )
}

function ScrapbookTemplate(props) {
  const {
    trip,
    journal,
    chapters,
    factCards,
    dateRangeLabel,
    galleryImages,
    totalPhotos,
    ownerName,
    editable,
    updateField,
    updateChapter,
    showProviderLabel,
  } = props

  const coverImage = journal?.content_json?.cover_image_url || trip?.cover_image_url

  return (
    <article className="journal-screen-book journal-shell journal-template-scrapbook">
      <section className="journal-hero journal-hero-scrapbook">
        <div className="journal-scrapbook-ornament journal-scrapbook-ornament-a" />
        <div className="journal-scrapbook-ornament journal-scrapbook-ornament-b" />
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(18rem,0.95fr)] lg:items-center">
          <div className="journal-scrapbook-copy">
            <div className="flex flex-wrap items-center gap-3">
              <div className="journal-pill">Memory Scrapbook</div>
              {showProviderLabel ? <div className="journal-provider-pill journal-provider-pill-light">{journal?.content_json?.provider_label || 'Story draft'}</div> : null}
            </div>
            <JournalInput
              editable={editable}
              value={journal.title}
              onChange={(value) => updateField('title', value)}
              className="mt-5 font-serif text-4xl font-semibold leading-tight text-slate-950 sm:text-5xl"
            />
            <p className="mt-4 max-w-2xl text-[15px] leading-7 text-slate-600">
              {dateRangeLabel}
              {ownerName ? ` / by ${ownerName}` : ''}
            </p>
            <div className="mt-6 rounded-[1.8rem] border border-[#eadfce] bg-white/85 px-5 py-5 shadow-sm">
              <p className="journal-section-eyebrow">Opening note</p>
              <JournalInput
                editable={editable}
                value={journal.intro_text || ''}
                onChange={(value) => updateField('intro_text', value)}
                className="mt-4 font-serif text-[17px] leading-8 text-slate-700 whitespace-pre-line"
                multiline
                rows={7}
              />
            </div>
          </div>
          <div className="journal-scrapbook-stack">
            {coverImage ? (
              <div className="journal-polaroid journal-polaroid-large">
                <img src={coverImage} alt={journal.title} className="journal-polaroid-image" />
                <div className="journal-polaroid-meta">
                  <span>Main cover</span>
                  <span>{trip?.title || 'Travel Diary'}</span>
                </div>
              </div>
            ) : null}
            <FactGrid factCards={factCards} templateKey="scrapbook" />
          </div>
        </div>
      </section>

      <div className="journal-paper px-6 py-8 sm:px-8 lg:px-10 lg:py-10">
        {trip?.travel_companions ? (
          <div className="journal-sticky-note">
            <Users className="h-4 w-4" />
            <div>
              <p className="journal-fact-label">Travel companions</p>
              <p className="mt-2 text-[15px] leading-7 text-slate-700">{trip.travel_companions}</p>
            </div>
          </div>
        ) : null}

        <MemoryGallery images={galleryImages} totalPhotos={totalPhotos} templateKey="scrapbook" />

        <div className="journal-divider"><span>Story cards</span></div>

        <div className="grid gap-6 xl:grid-cols-2">
          {chapters.map((chapter, index) => (
            <section key={`${chapter.visit_date}-${index}`} className="journal-chapter-card journal-chapter-scrapbook">
              {chapter.image_urls?.[0] ? (
                <div className="journal-scrapbook-image-frame">
                  <img src={chapter.image_urls[0]} alt={chapter.heading} className="journal-chapter-image" />
                </div>
              ) : null}
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="journal-section-eyebrow">Chapter {String(chapter.chapter_index || index + 1).padStart(2, '0')}</p>
                  <JournalInput
                    editable={editable}
                    value={chapter.heading || ''}
                    onChange={(value) => updateChapter(index, { heading: value })}
                    className="mt-2 font-serif text-3xl font-semibold leading-tight text-slate-900"
                  />
                </div>
                <div className="journal-date-chip">{formatVisitDate(chapter.visit_date)}</div>
              </div>
              <div className="journal-quote-card mt-5">
                <div className="journal-fact-icon"><Quote className="h-4 w-4" /></div>
                <JournalInput
                  editable={editable}
                  value={chapter.body_text || ''}
                  onChange={(value) => updateChapter(index, { body_text: value })}
                  className="font-serif text-[16px] leading-8 text-slate-700 whitespace-pre-line"
                  multiline
                  rows={7}
                />
              </div>
              {chapter.locations?.length ? (
                <div className="mt-5 flex flex-wrap gap-2">
                  {chapter.locations.map((location) => (
                    <span key={location.point_id} className="journal-location-chip">{location.place_name}</span>
                  ))}
                </div>
              ) : null}
            </section>
          ))}
        </div>

        <section className="journal-closing-card mt-10">
          <p className="journal-section-eyebrow">Final note</p>
          <JournalInput
            editable={editable}
            value={journal.closing_text || ''}
            onChange={(value) => updateField('closing_text', value)}
            className="mt-4 font-serif text-[18px] leading-9 text-slate-700 whitespace-pre-line"
            multiline
            rows={5}
          />
        </section>
      </div>
    </article>
  )
}

function FieldNotesTemplate(props) {
  const {
    trip,
    journal,
    chapters,
    factCards,
    dateRangeLabel,
    galleryImages,
    totalPhotos,
    ownerName,
    editable,
    updateField,
    updateChapter,
    showProviderLabel,
  } = props

  const coverImage = journal?.content_json?.cover_image_url || trip?.cover_image_url
  const heroTone = useImageTextTone(coverImage)
  const heroContrast = overlayToneClasses(heroTone)

  return (
    <article className="journal-screen-book journal-shell journal-template-field-notes">
      <section className="journal-hero journal-hero-field-notes">
        <div className="grid gap-6 xl:grid-cols-[16rem_minmax(0,1fr)]">
          <aside className="journal-field-sidebar">
            <div className="journal-pill">Field Notes</div>
            {showProviderLabel ? <div className="journal-provider-pill mt-4">{journal?.content_json?.provider_label || 'Story draft'}</div> : null}
            <div className="mt-8 space-y-4">
              {factCards.map(({ icon: Icon, label, value }) => (
                <div key={label} className="journal-field-fact">
                  <Icon className="h-4 w-4 text-sky-100" />
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-sky-100/70">{label}</p>
                    <p className="mt-1 text-sm font-semibold text-white">{value}</p>
                  </div>
                </div>
              ))}
            </div>
          </aside>
          <div className="journal-field-main">
            <div className="journal-field-cover">
              {coverImage ? <img src={coverImage} alt={journal.title} className="journal-hero-image" /> : null}
              <div className={`journal-hero-overlay ${heroContrast.overlay}`} />
              <div className="journal-field-cover-copy">
                <p className={`journal-section-eyebrow ${heroContrast.eyebrow}`}>Route story</p>
                <JournalInput
                  editable={editable}
                  value={journal.title}
                  onChange={(value) => updateField('title', value)}
                  className={`mt-4 font-serif text-4xl font-semibold leading-tight sm:text-5xl ${heroContrast.title}`}
                />
                <p className={`mt-4 text-[15px] leading-7 ${heroContrast.meta}`}>
                  {dateRangeLabel}
                  {ownerName ? ` / by ${ownerName}` : ''}
                </p>
              </div>
            </div>
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(16rem,0.8fr)]">
              <div className="journal-note-card">
                <p className="journal-section-eyebrow">Dispatch</p>
                <JournalInput
                  editable={editable}
                  value={journal.intro_text || ''}
                  onChange={(value) => updateField('intro_text', value)}
                  className="mt-4 font-serif text-[17px] leading-8 text-slate-700 whitespace-pre-line"
                  multiline
                  rows={7}
                />
              </div>
              {trip?.travel_companions ? (
                <div className="journal-side-card">
                  <div className="journal-fact-icon"><Users className="h-4 w-4" /></div>
                  <div>
                    <p className="journal-fact-label">Travel companions</p>
                    <p className="mt-2 text-[15px] leading-7 text-slate-700">{trip.travel_companions}</p>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <div className="journal-paper px-6 py-8 sm:px-8 lg:px-10 lg:py-10">
        <MemoryGallery images={galleryImages} totalPhotos={totalPhotos} templateKey="field-notes" />

        <div className="journal-divider"><span>Route log</span></div>

        <div className="space-y-6">
          {chapters.map((chapter, index) => (
            <section key={`${chapter.visit_date}-${index}`} className="journal-chapter-card journal-chapter-field-notes">
              <div className="journal-field-step">
                <div className="journal-field-step-index">{String(chapter.chapter_index || index + 1).padStart(2, '0')}</div>
                <div className="journal-field-step-line" />
              </div>
              <div className="min-w-0 flex-1 space-y-4">
                <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(18rem,0.85fr)] lg:items-start">
                  <div>
                    <p className="journal-section-eyebrow">Stage {String(chapter.chapter_index || index + 1).padStart(2, '0')}</p>
                    <JournalInput
                      editable={editable}
                      value={chapter.heading || ''}
                      onChange={(value) => updateChapter(index, { heading: value })}
                      className="mt-2 font-serif text-3xl font-semibold leading-tight text-slate-900"
                    />
                    <p className="mt-3 text-sm text-slate-400">{formatVisitDate(chapter.visit_date)}</p>
                    <div className="journal-quote-card mt-5">
                      <div className="journal-fact-icon"><Quote className="h-4 w-4" /></div>
                      <JournalInput
                        editable={editable}
                        value={chapter.body_text || ''}
                        onChange={(value) => updateChapter(index, { body_text: value })}
                        className="font-serif text-[16px] leading-8 text-slate-700 whitespace-pre-line"
                        multiline
                        rows={7}
                      />
                    </div>
                  </div>
                  <div className="space-y-4">
                    {chapter.image_urls?.[0] ? (
                      <div className="overflow-hidden rounded-[1.75rem] border border-[#d9e3f2] bg-slate-100">
                        <img src={chapter.image_urls[0]} alt={chapter.heading} className="h-64 w-full object-cover" />
                      </div>
                    ) : null}
                    {chapter.locations?.length ? (
                      <div className="rounded-[1.5rem] border border-[#d9e3f2] bg-[#f8fbff] p-4">
                        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                          <MapPinned className="h-4 w-4" />
                          Stops on this leg
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {chapter.locations.map((location) => (
                            <span key={location.point_id} className="journal-location-chip">{location.place_name}</span>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            </section>
          ))}
        </div>

        <section className="journal-closing-card mt-10">
          <p className="journal-section-eyebrow">Return note</p>
          <JournalInput
            editable={editable}
            value={journal.closing_text || ''}
            onChange={(value) => updateField('closing_text', value)}
            className="mt-4 font-serif text-[18px] leading-9 text-slate-700 whitespace-pre-line"
            multiline
            rows={5}
          />
        </section>
      </div>
    </article>
  )
}

export default function JournalRenderer({
  trip,
  journal,
  ownerName = '',
  editable = false,
  onChange,
  showProviderLabel = true,
}) {
  const chapters = journal?.content_json?.chapters || []
  const templateKey = journal?.content_json?.template_key || 'editorial'
  const totalPhotos = chapters.reduce((count, chapter) => count + (chapter.image_urls?.length || 0), 0)
  const totalLocations = chapters.reduce((count, chapter) => count + (chapter.locations?.length || 0), 0)
  const galleryImages = uniqueImagesFromChapters(chapters)
  const dateRangeLabel = fmtDateRange(trip?.start_date, trip?.end_date) || 'Dates not set'

  const updateField = (field, value) => {
    if (!editable || !onChange) return
    onChange({ ...journal, [field]: value })
  }

  const updateChapter = (index, patch) => {
    if (!editable || !onChange) return
    const nextChapters = chapters.map((chapter, chapterIndex) => (
      chapterIndex === index ? { ...chapter, ...patch } : chapter
    ))
    onChange({
      ...journal,
      content_json: {
        ...(journal.content_json || {}),
        template_key: templateKey,
        chapters: nextChapters,
      },
    })
  }

  const factCards = [
    { icon: CalendarDays, label: 'Travel window', value: dateRangeLabel },
    { icon: MapPinned, label: 'Places captured', value: `${totalLocations || trip?.timeline_points?.length || 0} stops` },
    { icon: Camera, label: 'Photo memories', value: `${totalPhotos} photo${totalPhotos === 1 ? '' : 's'}` },
    { icon: Route, label: 'Story chapters', value: `${chapters.length} chapter${chapters.length === 1 ? '' : 's'}` },
  ]

  const templateProps = {
    trip,
    journal,
    chapters,
    factCards,
    dateRangeLabel,
    galleryImages,
    totalPhotos,
    ownerName,
    editable,
    updateField,
    updateChapter,
    showProviderLabel,
  }

  if (templateKey === 'scrapbook') return <ScrapbookTemplate {...templateProps} />
  if (templateKey === 'field_notes') return <FieldNotesTemplate {...templateProps} />
  return <EditorialTemplate {...templateProps} />
}
