import { Link } from 'react-router-dom'
import { Globe, Map, Clock, Share2, ChevronRight } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const FEATURES = [
  { Icon: Globe,  title: 'World Map',    desc: 'See all your visits pinned on an interactive world map with color-coded travel routes.' },
  { Icon: Clock,  title: 'Timeline',     desc: 'Relive your journey as a beautiful chronological story with photos and descriptions.' },
  { Icon: Map,    title: 'Route Planner',desc: 'Track every leg of your trip — flight, train, car, ferry, walk, and more.' },
  { Icon: Share2, title: 'Public Sharing',desc: 'Share your trip with a public link so others can explore your adventure.' },
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
                <Link to="/login"    className="text-sm font-medium text-slate-600 hover:text-primary-600">Sign in</Link>
                <Link to="/register" className="bg-primary-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors">
                  Get started
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="bg-gradient-to-br from-primary-900 via-primary-700 to-sky-600 text-white py-24 px-4">
        <div className="max-w-3xl mx-auto text-center space-y-6">
          <div className="inline-flex items-center gap-2 bg-white/10 px-3 py-1 rounded-full text-sm">
            <Globe className="w-4 h-4" />
            Your personal travel timeline + world map diary
          </div>
          <h1 className="text-4xl sm:text-5xl font-bold leading-tight">
            Pin your memories on a<br />
            <span className="text-sky-300">world map</span>
          </h1>
          <p className="text-lg text-white/80 max-w-xl mx-auto">
            Create visual travel timelines, track routes between places, upload photos,
            and share your journeys with the world.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link to="/register" className="bg-white text-primary-700 font-semibold px-6 py-3 rounded-lg hover:bg-white/90 transition-colors flex items-center gap-2">
              Start for free <ChevronRight className="w-4 h-4" />
            </Link>
            <Link to="/login" className="border border-white/30 text-white font-medium px-6 py-3 rounded-lg hover:bg-white/10 transition-colors">
              Sign in
            </Link>
          </div>
        </div>
      </section>

      {/* Example route */}
      <section className="bg-slate-900 text-white py-6 px-4 overflow-hidden">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center gap-2 text-sm text-slate-300 overflow-x-auto whitespace-nowrap pb-1 justify-center">
            {['Kuala Lumpur ✈️', 'Doha ✈️', 'Zurich 🚆', 'Lucerne 🚆', 'Interlaken 🚆', 'Lauterbrunnen'].map((s, i) => (
              <span key={i} className="flex items-center gap-2">
                <span className="text-slate-400 bg-slate-800 px-3 py-1 rounded-full">{s}</span>
                {i < 5 && <span className="text-slate-600">→</span>}
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
        Travel Diary · Built with FastAPI + React + Leaflet.js
      </footer>
    </div>
  )
}
