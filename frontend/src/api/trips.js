import client from './client'

export const tripsApi = {
  list:   ()           => client.get('/trips').then(r => r.data),
  get:    (id)         => client.get(`/trips/${id}`).then(r => r.data),
  create: (data)       => client.post('/trips', data).then(r => r.data),
  update: (id, data)   => client.put(`/trips/${id}`, data).then(r => r.data),
  regenerateShare: (id) => client.post(`/trips/${id}/share/regenerate`).then(r => r.data),
  getJournal: (id)     => client.get(`/trips/${id}/journal`).then(r => r.data),
  generateJournal: (id, data) => client.post(`/trips/${id}/journal/generate`, data).then(r => r.data),
  updateJournal: (id, data) => client.put(`/trips/${id}/journal`, data).then(r => r.data),
  delete: (id)         => client.delete(`/trips/${id}`),
}
