// TEMPORARY — AggregateX migration placeholder. Delete this file once the AggregateX backend exists.
//
// The old Revelio/WitnessTrace backend was removed and the new backend is not built yet. While
// `previewMode` is on, both API clients (src/api/client.js, src/api/witnesstrace.js) call
// `previewFetch` instead of the network, so no request leaves the browser.
//
// It holds no fake records, metrics or statuses. Every call answers 503 "no backend connected",
// so pages show their existing offline, error and empty states. The one exception is the session
// check, which returns a clearly labelled preview user so the workspace can be browsed.
//
// Set VITE_BACKEND_ENABLED=1 (and add a dev proxy in vite.config.js) to talk to a real backend.

// The AgrregateX API now exists (hackathon/app). Preview mode is opt-in: VITE_BACKEND_ENABLED=0.
export const previewMode = import.meta.env?.VITE_BACKEND_ENABLED === '0'

export const NO_BACKEND = 'No backend connected. The AggregateX backend has not been implemented yet, so this is unavailable in preview mode.'

export const PREVIEW_USER = Object.freeze({ id: 'preview', name: 'Preview user', email: 'preview@localhost', preview: true })

const json = (value, status) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })

/** fetch-compatible stand-in for the removed backend. */
export async function previewFetch(url, init = {}) {
  const path = new URL(url, 'http://preview.invalid').pathname
  const method = (init.method || 'GET').toUpperCase()
  if (method === 'GET' && path.endsWith('/auth/me')) return json({ user: PREVIEW_USER }, 200)
  return json({ detail: NO_BACKEND, preview: true }, 503)
}
