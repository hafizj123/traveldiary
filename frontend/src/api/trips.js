import client from './client'

export const tripsApi = {
  list:   ()           => client.get('/trips').then(r => r.data),
  get:    (id)         => client.get(`/trips/${id}`).then(r => r.data),
  create: (data)       => client.post('/trips', data).then(r => r.data),
  update: (id, data)   => client.put(`/trips/${id}`, data).then(r => r.data),
  delete: (id)         => client.delete(`/trips/${id}`),
}
