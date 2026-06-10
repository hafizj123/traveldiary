import client from './client'

export const routesApi = {
  train: (params) => client.get('/routes/train', { params }).then((r) => r.data),
  ferry: (params) => client.get('/routes/ferry', { params }).then((r) => r.data),
  nearestTrainStation: (params) => client.get('/stations/nearest-train', { params }).then((r) => r.data),
  reverseLocation: (params) => client.get('/locations/reverse', { params }).then((r) => r.data),
  nearestTransportPlace: (params) => client.get('/locations/nearest-transport', { params }).then((r) => r.data),
}
