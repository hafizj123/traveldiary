import client from './client'

const UPLOAD_TIMEOUT_MS = 120000

function normalizeUploadError(error) {
  if (error.code === 'ECONNABORTED') {
    return new Error('Upload timed out. Please try a smaller image or a stronger connection.')
  }

  const detail = error.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) {
    return new Error(detail)
  }

  return new Error('Upload failed. Please try again.')
}

export const uploadApi = {
  image: (file) => {
    const form = new FormData()
    form.append('file', file)
    return client.post('/upload/image', form, {
      timeout: UPLOAD_TIMEOUT_MS,
    })
      .then(r => r.data)
      .catch((error) => Promise.reject(normalizeUploadError(error)))
  },
  deleteImage: (url) =>
    client.delete('/upload/image', { data: { url } }).then(r => r.data),
}
