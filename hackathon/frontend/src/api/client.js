// Thin client for the AggregateX API (hackathon/app). The session is an HttpOnly cookie
// that page scripts cannot read; tenant scoping is enforced by the API and by database RLS.


const BASE = (import.meta.env?.VITE_API_BASE || '/api').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(status, message, data) {
    super(message)
    this.status = status
    this.data = data || {}
  }

  get isOffline() {
    return this.status === 0
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  let res
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      signal,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (err) {
    if (err?.name === 'AbortError') throw err
    throw new ApiError(0, 'The AggregateX API is not reachable.')
  }
  if (!res.ok) {
    let data = {}
    try {
      data = await res.json()
    } catch {
      /* non-JSON error body */
    }
    const detail = typeof data.detail === 'string' ? data.detail : `Request failed (${res.status})`
    throw new ApiError(res.status, detail, data)
  }
  if (res.status === 204) return null
  return res.json()
}

// Builds "?from=..&to=.." from an object, skipping empty values.
export const query = (params = {}) => {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v != null && v !== '') q.set(k, v)
  const qs = q.toString()
  return qs ? `?${qs}` : ''
}
const T = (id) => `/tenants/${encodeURIComponent(id)}`

export const api = {
  monitoring: (signal) => request('/monitoring', { signal }),
  me: () => request('/auth/me'),
  login: (email, password) => request('/auth/login', { method: 'POST', body: { email, password } }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  health: (signal) => request('/health', { signal }),

  tenants: () => request('/tenants'),
  summary: (t, r, signal) => request(`${T(t)}/summary${query(r)}`, { signal }),
  trends: (t, r, signal) => request(`${T(t)}/trends${query(r)}`, { signal }),
  topProducts: (t, r, signal) => request(`${T(t)}/top-products${query(r)}`, { signal }),
  breakdown: (t, r, signal) => request(`${T(t)}/breakdown${query(r)}`, { signal }),
  freshness: (t, signal) => request(`${T(t)}/freshness`, { signal }),
  liveWrite: (t, body) => request(`${T(t)}/live-write`, { method: 'POST', body }),
  // B-4: metric definitions come from the server's config file, not from this client.
  metrics: (signal) => request('/metrics', { signal }),
  metric: (t, id, r, signal) => request(`${T(t)}/metrics/${encodeURIComponent(id)}${query(r)}`, { signal }),

  engine: (shard, signal) => request(`/engine${query({ shard })}`, { signal }),
  shards: (signal) => request('/shards', { signal }),
  limits: (signal) => request('/limits', { signal }),
}
