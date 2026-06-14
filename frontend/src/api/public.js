import client from './client'

export const publicApi = {
  profile: (username)             => client.get(`/u/${username}`).then(r => r.data),
  trip:    (username, tripId)     => client.get(`/u/${username}/trips/${tripId}`).then(r => r.data),
  tripJournal: (username, tripId) => client.get(`/u/${username}/trips/${tripId}/journal`).then(r => r.data),
  sharedTrip: (shareSlug)         => client.get(`/shared/${shareSlug}`).then(r => r.data),
  sharedTripJournal: (shareSlug)  => client.get(`/shared/${shareSlug}/journal`).then(r => r.data),
  sharedTrips: (params)           => client.get('/shared-trips', { params }).then(r => r.data),
}
