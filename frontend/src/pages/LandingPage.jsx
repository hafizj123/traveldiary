import { Link } from 'react-router-dom'
import { Globe, Map, Clock, Share2, ChevronRight } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import heroImage from '../image/pexels-marina-zasorina-7634437.jpg'

const FEATURES = [
  { Icon: Globe, title: 'World Map', desc: 'See all your visits pinned on an interactive world map with color-coded travel routes.' },
  { Icon: Clock, title: 'Timeline', desc: 'Relive your journey as a beautiful chronological story with photos and descriptions.' },
  { Icon: Map, title: 'Route Planner', desc: 'Track every leg of your trip - flight, train, car, ferry, walk, and more.' },
  { Icon: Share2, title: 'Public Sharing', desc: 'Share your trip with a public link so others can explore your adventure.' },
]

export default function LandingPage() {
  const { user } = useAuth()

  return (
    <div className="min-h-screen">
      {/* Navbar */}
      <header className="bg-white border-b border-slate-100 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex h-16 items-center justify-between">
          <div className="flex items-center gap-2 font-bold text-primary-600 text-lg">
            <Globe className="w-6 h-6" />
            Travel Diary
          </div>
          <div className="flex items-center gap-3">
            {user ? (
              <Link to="/dashboard" className="bg-primary-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors">
                Go to Dashboard
              </Link>
            ) : (
              <>
                <Link to="/login" className="text-sm font-medium text-slate-600 hover:text-primary-600">Sign in</Link>
                <Link to="/register" className="bg-primary-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors">
                  Get started
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <div
          className="relative mx-auto max-w-7xl overflow-hidden rounded-[2rem] text-white shadow-2xl shadow-slate-900/20"
          style={{ backgroundImage: `url(${heroImage})`, backgroundSize: 'cover', backgroundPosition: 'center' }}
        >
          <div className="absolute inset-0 bg-gradient-to-br from-slate-950/72 via-primary-900/50 to-sky-900/62" />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.18),transparent_32%),radial-gradient(circle_at_bottom_right,rgba(56,189,248,0.24),transparent_28%)]" />
          <div className="relative px-6 py-16 sm:px-10 lg:px-14 lg:py-24">
            <div className="max-w-3xl space-y-6">
              <div className="inline-flex items-center gap-2 rounded-full bg-white/12 px-4 py-2 text-sm backdrop-blur-sm">
                <Globe className="w-4 h-4" />
                Your personal travel timeline + world map diary
              </div>
              <h1 className="text-4xl font-bold leading-tight sm:text-5xl lg:text-6xl">
                Pin your memories on a
                <br />
                world map
              </h1>
              <p className="max-w-2xl text-base leading-7 text-white/82 sm:text-lg">
                Create visual travel timelines, track routes between places, upload photos,
                and share your journeys with the world.
              </p>
              <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                <Link to="/register" className="inline-flex items-center justify-center gap-2 rounded-full bg-white px-6 py-3 font-semibold text-slate-900 hover:bg-white/92 transition-colors">
                  Start for free <ChevronRight className="w-4 h-4" />
                </Link>
                <Link to="/shared-trips" className="inline-flex items-center justify-center rounded-full border border-white/30 bg-white/10 px-6 py-3 font-medium text-white backdrop-blur-sm hover:bg-white/16 transition-colors">
                  Explore shared trips
                </Link>
                <Link to="/login" className="inline-flex items-center justify-center rounded-full border border-white/20 px-6 py-3 font-medium text-white/92 hover:bg-white/10 transition-colors">
                  Sign in
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Example route */}
      <section className="bg-slate-900 text-white py-6 px-4 overflow-hidden">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center gap-2 text-sm text-slate-300 overflow-x-auto whitespace-nowrap pb-1 justify-center">
            {['Kuala Lumpur (Flight)', 'Doha (Flight)', 'Zurich (Train)', 'Lucerne (Train)', 'Interlaken (Train)', 'Lauterbrunnen'].map((s, i) => (
              <span key={i} className="flex items-center gap-2">
                <span className="text-slate-400 bg-slate-800 px-3 py-1 rounded-full">{s}</span>
                {i < 5 && <span className="text-slate-600">-&gt;</span>}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-20 px-4 bg-white">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-center text-2xl font-bold text-slate-800 mb-12">Everything you need to document your travels</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {FEATURES.map(({ Icon, title, desc }) => (
              <div key={title} className="p-6 rounded-xl border border-slate-100 hover:border-primary-200 hover:shadow-md transition-all">
                <div className="w-10 h-10 bg-primary-50 rounded-lg flex items-center justify-center mb-4">
                  <Icon className="w-5 h-5 text-primary-600" />
                </div>
                <h3 className="font-semibold text-slate-800 mb-2">{title}</h3>
                <p className="text-sm text-slate-500 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-16 px-4 bg-primary-50">
        <div className="max-w-xl mx-auto text-center space-y-4">
          <h2 className="text-2xl font-bold text-slate-800">Ready to map your adventures?</h2>
          <p className="text-slate-500">Free to use. No credit card required.</p>
          <Link to="/register" className="inline-flex items-center gap-2 bg-primary-600 text-white font-semibold px-8 py-3 rounded-lg hover:bg-primary-700 transition-colors">
            Create your travel diary <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      </section>

      <footer className="text-center py-8 text-sm text-slate-400 border-t border-slate-100">
        Travel Diary - Built with FastAPI + React + Leaflet.js
      </footer>
    </div>
  )
}
