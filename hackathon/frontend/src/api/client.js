// Thin client for the local Revelio API. No provider credentials ever pass
// through the browser: hosted providers are configured on the backend only.
// The session lives in an HttpOnly cookie that page scripts cannot read.
import { loginUrl } from '../lib/auth'
import { previewFetch, previewMode } from '../services/previewBackend'

const BASE = (import.meta.env.VITE_API_BASE || '/api').replace(/\/$/, '')
// AggregateX migration: no backend exists yet, so preview mode answers locally (see services/previewBackend.js).
const send = previewMode ? previewFetch : (...args) => fetch(...args)

export class ApiError extends Error {
  constructor(status, message, data) {
    super(message)
    this.status = status
    this.data = data || {}
  }

  get isProviderError() {
    return Boolean(this.data?.provider_error)
  }

  get isOffline() {
    return this.status === 0
  }
}

async function request(path, { method = 'GET', body, blob, signal, raw = false } = {}) {
  let res
  try {
    res = await send(`${BASE}${path}`, {
      method,
      signal,
      headers: body !== undefined ? { 'Content-Type': 'application/json' }
        : blob ? { 'Content-Type': blob.type || 'application/octet-stream' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : blob,
    })
  } catch (err) {
    if (err?.name === 'AbortError') throw err
    throw new ApiError(0, 'The backend is not reachable.')
  }
  if (!res.ok) {
    // Session expired or logged out elsewhere: send the workspace back to the login page.
    if (res.status === 401 && !path.startsWith('/auth/') && window.location.pathname.startsWith('/app')) {
      window.location.assign(loginUrl())
    }
    let data = {}
    try {
      data = await res.json()
    } catch {
      /* non-JSON error body */
    }
    const detail = typeof data.detail === 'string' ? data.detail : `Request failed (${res.status})`
    throw new ApiError(res.status, detail, data)
  }
  if (raw) return res
  if (res.status === 204) return null
  return res.json()
}

/** Resolve an API-relative asset path (e.g. image URLs returned by the API). */
export const assetUrl = (path) => {
  if (!path) return null
  if (BASE === '/api') return path
  return BASE.replace(/\/api$/, '') + path
}

const range = (r = {}) => {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(r)) if (v != null && v !== '') q.set(k, v)
  const qs = q.toString()
  return qs ? `?${qs}` : ''
}
const T = (id) => `/tenants/${encodeURIComponent(id)}`

export const api = {
  // ── AgrregateX analytics (hackathon/app) ──
  tenants: () => request('/tenants'),
  summary: (t, r, signal) => request(`${T(t)}/summary${range(r)}`, { signal }),
  trends: (t, r, signal) => request(`${T(t)}/trends${range(r)}`, { signal }),
  topProducts: (t, r, signal) => request(`${T(t)}/top-products${range(r)}`, { signal }),
  breakdown: (t, r, signal) => request(`${T(t)}/breakdown${range(r)}`, { signal }),
  freshness: (t, signal) => request(`${T(t)}/freshness`, { signal }),
  liveWrite: (t, body) => request(`${T(t)}/live-write`, { method: 'POST', body }),
  engine: (shard, signal) => request(`/engine${shard ? `?shard=${encodeURIComponent(shard)}` : ''}`, { signal }),
  shards: (signal) => request('/shards', { signal }),

  // ── legacy Revelio endpoints (no longer served) ──
  me: () => request('/auth/me'),
  register: (name, email, password) => request('/auth/register', { method: 'POST', body: { name, email, password } }),
  login: (email, password) => request('/auth/login', { method: 'POST', body: { email, password } }),
  logout: () => request('/auth/logout', { method: 'POST' }),

  health: (signal) => request('/health', { signal }),
  speech: () => request('/speech'),
  transcribe: (audio, lang) => request(`/speech/transcribe?lang=${encodeURIComponent(lang || '')}`, { method: 'POST', blob: audio }),
  catalog: () => request('/catalog'),
  stats: () => request('/stats'),
  activity: (limit = 20) => request(`/activity?limit=${limit}`),
  storage: () => request('/storage'),

  extract: (description) => request('/traits/extract', { method: 'POST', body: { description } }),
  merge: (descriptions) => request('/witnesses/merge', { method: 'POST', body: { descriptions } }),
  parseRefine: (instruction, profile) => request('/refine/parse', { method: 'POST', body: { instruction, profile } }),
  applyRefine: (profile, changes) => request('/refine/apply', { method: 'POST', body: { profile, changes } }),

  render: (profile, caption, signal) => request('/render', { method: 'POST', body: { profile, caption }, signal }),
  renderPng: async (profile, caption) => {
    const res = await request('/render.png', { method: 'POST', body: { profile, caption }, raw: true })
    return res.blob()
  },

  listSketches: (q) => request(`/sketches${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  getSketch: (id) => request(`/sketches/${encodeURIComponent(id)}`),
  generate: (payload) => request('/sketches/generate', { method: 'POST', body: payload }),
  addRevision: (id, payload) => request(`/sketches/${encodeURIComponent(id)}/revisions`, { method: 'POST', body: payload }),
  updateSketch: (id, patch) => request(`/sketches/${encodeURIComponent(id)}`, { method: 'PATCH', body: patch }),
  deleteSketch: (id) => request(`/sketches/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  deleteAll: () => request('/data/delete-all', { method: 'POST', body: { confirm: 'DELETE' } }),

  exportJsonUrl: (id) => `${BASE}/sketches/${encodeURIComponent(id)}/export.json?download=true`,
  reportUrl: (id) => `${BASE}/sketches/${encodeURIComponent(id)}/report`,
  pngDownloadUrl: (id, n) => `${BASE}/sketches/${encodeURIComponent(id)}/revisions/${n}/image.png?download=true`,
}
