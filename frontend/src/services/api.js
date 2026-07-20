const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
    },
  })

  if (!response.ok) {
    let message = `요청을 처리하지 못했습니다. (${response.status})`
    try {
      const payload = await response.json()
      if (Array.isArray(payload.detail)) {
        message = payload.detail.map((item) => item.msg).filter(Boolean).join(' · ') || message
      } else {
        message = payload.detail || message
      }
    } catch {
      // JSON 오류 본문이 아니면 기본 메시지를 사용합니다.
    }
    throw new Error(message)
  }
  if (response.status === 204) return null
  return response.json()
}

export const api = {
  health: () => request('/health'),
  sessions: () => request('/sessions'),
  session: (id) => request(`/sessions/${id}`),
  createSession: (payload) =>
    request('/sessions', { method: 'POST', body: JSON.stringify(payload) }),
  createDemo: () => request('/sessions/demo', { method: 'POST' }),
  updateStatus: (id, payload) =>
    request(`/sessions/${id}/status`, { method: 'PATCH', body: JSON.stringify(payload) }),
  appendTranscript: (id, payload) =>
    request(`/sessions/${id}/transcript`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  uploadAudio: (id, blob, startSeconds) => {
    const data = new FormData()
    const extension = blob.type.includes('ogg') ? 'ogg' : 'webm'
    data.append('audio', blob, `lecture-${Date.now()}.${extension}`)
    data.append('start_seconds', String(startSeconds))
    return request(`/sessions/${id}/audio`, { method: 'POST', body: data })
  },
  refreshSummary: (id) => request(`/sessions/${id}/summary`, { method: 'POST' }),
  chat: (id, message) =>
    request(`/sessions/${id}/chat`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  deleteSession: (id) => request(`/sessions/${id}`, { method: 'DELETE' }),
}
