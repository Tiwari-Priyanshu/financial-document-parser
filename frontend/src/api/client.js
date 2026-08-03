import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

const TOKEN_KEY = 'findoc_token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

// Attach the JWT to every outgoing request. Doing it in an interceptor rather
// than at each call site means no endpoint can accidentally forget it.
api.interceptors.request.use((config) => {
  const token = tokenStore.get()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// A 401 means the token expired or was revoked server-side. Clear it and send
// the user to login rather than letting the UI show confusing empty states.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !error.config?.url?.includes('/auth/')) {
      tokenStore.clear()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

/**
 * Turn any API failure into a single readable string.
 *
 * The backend returns three different error shapes: a plain {detail: "..."},
 * a structured {detail: {message, code}}, and a validation
 * {detail, errors: [{field, message}]}. Handling that here means components
 * never have to.
 */
export function errorMessage(error, fallback = 'Something went wrong') {
  const data = error?.response?.data
  if (!data) {
    return error?.message === 'Network Error'
      ? 'Cannot reach the server. Is the backend running?'
      : fallback
  }
  if (Array.isArray(data.errors) && data.errors.length) {
    return data.errors.map((e) => `${e.field}: ${e.message}`).join(', ')
  }
  const detail = data.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  return fallback
}

export const auth = {
  register: (payload) => api.post('/api/auth/register', payload),
  login: (payload) => api.post('/api/auth/login', payload),
  profile: () => api.get('/api/auth/profile'),
  updateProfile: (payload) => api.put('/api/auth/profile', payload),
}

export const documents = {
  list: (params) => api.get('/api/documents', { params }),
  get: (id) => api.get(`/api/documents/${id}`),
  remove: (id) => api.delete(`/api/documents/${id}`),
  upload: (file, onProgress) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/api/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (event) => {
        if (onProgress && event.total) {
          onProgress(Math.round((event.loaded * 100) / event.total))
        }
      },
    })
  },
}

export const parser = {
  status: (id) => api.get(`/api/parser/status/${id}`),
  result: (id) => api.get(`/api/parser/result/${id}`),
  process: (id) => api.post(`/api/parser/process/${id}`),
  reprocess: (id, documentType) =>
    api.post(`/api/parser/reprocess/${id}`, { document_type: documentType || null }),
  updateFields: (id, corrections, remarks) =>
    api.put(`/api/parser/result/${id}/fields`, { corrections, remarks }),
  approve: (id, remarks) =>
    api.post(`/api/parser/result/${id}/approve`, { remarks }),
  reject: (id, remarks) =>
    api.post(`/api/parser/result/${id}/reject`, { remarks }),
}

export const dashboard = {
  stats: (days = 30) => api.get('/api/dashboard', { params: { days } }),
}

export const logs = {
  list: (params) => api.get('/api/logs', { params }),
  forDocument: (id) => api.get(`/api/logs/document/${id}`),
}

export const reports = {
  list: (params) => api.get('/api/reports', { params }),
  /**
   * Downloads go through Axios rather than a plain link because the endpoint
   * needs the Authorization header - a bare <a href> cannot send one.
   * The blob is turned into a temporary object URL to trigger the save.
   */
  download: async (id, format, filename) => {
    const path = { pdf: 'pdf', excel: 'excel', csv: 'csv' }[format]
    const response = await api.get(`/api/reports/export/${path}/${id}`, {
      responseType: 'blob',
    })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.download = filename || `report.${format === 'excel' ? 'xlsx' : format}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  },
}
