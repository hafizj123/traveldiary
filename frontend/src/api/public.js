import client from './client'

export const publicApi = {
  profile: (username)         => client.get(`/u/${username}`).then(r => r.data),
  trip:    (username, tripId) => client.get(`/u/${username}/trips/${tripId}`).then(r => r.data),
}
