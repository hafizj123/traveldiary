import client from './client'

export const routesApi = {
  train: (params) => client.get('/routes/train', { params }).then((r) => r.data),
}
