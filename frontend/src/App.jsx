import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import ProtectedRoute from './components/layout/ProtectedRoute'

import LandingPage      from './pages/LandingPage'
import LoginPage        from './pages/auth/LoginPage'
import RegisterPage     from './pages/auth/RegisterPage'
import VerifyOTPPage    from './pages/auth/VerifyOTPPage'
import DashboardPage    from './pages/DashboardPage'
import TripsPage        from './pages/trips/TripsPage'
import CreateTripPage   from './pages/trips/CreateTripPage'
import EditTripPage     from './pages/trips/EditTripPage'
import TripDetailPage   from './pages/trips/TripDetailPage'
import TripJournalPage  from './pages/trips/TripJournalPage'
import AddPointPage     from './pages/points/AddPointPage'
import EditPointPage    from './pages/points/EditPointPage'
import SavedRoutesPage  from './pages/routes/SavedRoutesPage'
import GeoJsonImportPage from './pages/routes/GeoJsonImportPage'
import AdminToolsPage from './pages/routes/AdminToolsPage'
import PublicProfilePage from './pages/public/PublicProfilePage'
import PublicTripPage   from './pages/public/PublicTripPage'
import SharedTripsPage from './pages/public/SharedTripsPage'
import PublicJournalPage from './pages/public/PublicJournalPage'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public */}
          <Route path="/"            element={<LandingPage />} />
          <Route path="/login"       element={<LoginPage />} />
          <Route path="/register"    element={<RegisterPage />} />
          <Route path="/verify-otp"  element={<VerifyOTPPage />} />
          <Route path="/shared-trips" element={<SharedTripsPage />} />
          <Route path="/shared/:shareSlug" element={<PublicTripPage />} />
          <Route path="/shared/:shareSlug/journal" element={<PublicJournalPage />} />
          <Route path="/u/:username" element={<PublicProfilePage />} />
          <Route path="/u/:username/trips/:tripId" element={<PublicTripPage />} />
          <Route path="/u/:username/trips/:tripId/journal" element={<PublicJournalPage />} />

          {/* Protected */}
          <Route element={<ProtectedRoute />}>
            <Route path="/dashboard"                            element={<DashboardPage />} />
            <Route path="/trips"                                element={<TripsPage />} />
            <Route path="/trips/new"                            element={<CreateTripPage />} />
            <Route path="/trips/:tripId"                        element={<TripDetailPage />} />
            <Route path="/trips/:tripId/edit"                   element={<EditTripPage />} />
            <Route path="/trips/:tripId/journal"                element={<TripJournalPage />} />
            <Route path="/trips/:tripId/points/new"             element={<AddPointPage />} />
            <Route path="/trips/:tripId/points/:pointId/edit"   element={<EditPointPage />} />
            <Route path="/saved-routes"                         element={<SavedRoutesPage />} />
            <Route path="/geojson-imports"                      element={<GeoJsonImportPage />} />
            <Route path="/admin-tools"                          element={<AdminToolsPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
