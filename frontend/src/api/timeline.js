import client from './client'

export const timelineApi = {
  listPoints:    (tripId)           => client.get(`/trips/${tripId}/points`).then(r => r.data),
  addPoint:      (tripId, data)     => client.post(`/trips/${tripId}/points`, data).then(r => r.data),
  reorderPoints: (tripId, pointIds) => client.post(`/trips/${tripId}/points/reorder`, { point_ids: pointIds }).then(r => r.data),
  updatePoint:   (pointId, data)    => client.put(`/points/${pointId}`, data).then(r => r.data),
  deletePoint:   (pointId)          => client.delete(`/points/${pointId}`),

  listSegments:  (tripId)           => client.get(`/trips/${tripId}/segments`).then(r => r.data),
  createSegment: (tripId, data)     => client.post(`/trips/${tripId}/segments`, data).then(r => r.data),
  updateSegment: (segId, data)      => client.put(`/segments/${segId}`, data).then(r => r.data),
  deleteSegment: (segId)            => client.delete(`/segments/${segId}`),
}
