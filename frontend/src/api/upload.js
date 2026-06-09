import client from './client'

export const uploadApi = {
  image: (file) => {
    const form = new FormData()
    form.append('file', file)
    return client.post('/upload/image', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
  deleteImage: (url) =>
    client.delete('/upload/image', { data: { url } }).then(r => r.data),
}
