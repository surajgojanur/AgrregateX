// Same-origin, authenticated gateway. No arbitrary upstream URLs or browser credentials.
import { previewFetch, previewMode } from '../services/previewBackend.js'
// Legacy Revelio/WitnessTrace client: off unless explicitly enabled.
export const witnessMode = import.meta.env?.VITE_WITNESSTRACE_LOCAL === '1'
const BASE = '/wt-api'
const ID = /^[a-f0-9]{32}$/
const identifier = (id) => { if (!ID.test(id)) throw new WitnessError(400, 'Invalid record identifier.'); return id }
export class WitnessError extends Error {
  constructor(status, message) { super(message); this.status = status }
}
export function createWitnessClient(fetcher = (...args) => fetch(...args), timeout = 15000) {
  async function request(path, { body, signal, method, validate = () => true } = {}) {
    const controller = new AbortController()
    const abort = () => controller.abort(signal.reason)
    if (signal?.aborted) abort()
    signal?.addEventListener('abort', abort, { once: true })
    const timer = setTimeout(() => controller.abort(), timeout)
    try {
      const response = await fetcher(BASE + path, { method: method || (body === undefined ? 'GET' : 'POST'),
        credentials: 'same-origin', signal: controller.signal,
        headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) })
      let value
      try { value = await response.json() } catch { throw new WitnessError(response.status, 'Invalid response from WitnessTrace.') }
      if (!response.ok) {
        const detail = Array.isArray(value.detail) ? value.detail.map(e => e.msg).join('; ') : value.detail
        throw new WitnessError(response.status, response.status === 401 ? 'Session expired. Sign in again.' : (typeof detail === 'string' ? detail : `Request failed (${response.status}).`))
      }
      let valid = false
      try { valid = Boolean(validate(value)) } catch { /* malformed nested payload */ }
      if (!valid) throw new WitnessError(502, 'Unexpected WitnessTrace response. Reconnect before continuing.')
      return value
    } catch (error) {
      if (signal?.aborted) throw new DOMException('Polling stopped', 'AbortError')
      if (error instanceof WitnessError) throw error
      throw new WitnessError(0, controller.signal.aborted ? 'Request timed out. Check existing jobs before submitting again.' : 'WitnessTrace connection lost. Reconnect without resubmitting.')
    } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort) }
  }
  const isCase = v => ID.test(v?.id) && Number.isInteger(v.revision) && Array.isArray(v.versions) && v.versions.every(r => ID.test(r.id) && r.image_url === `/images/${r.id}`) && Array.isArray(v.jobs) && v.jobs.every(j => ID.test(j.id)) && Array.isArray(v.statements) && v.statements.every(s => typeof s.text === 'string') && v.draft && typeof v.draft === 'object'
  const isJob = v => ID.test(v?.job_id) && ['working', 'complete', 'failed'].includes(v.status) && (v.status !== 'complete' || v.image_url === `/images/${v.job_id}`)
  return {
    operation: (path, body, method) => request(path, { body, method }),
    health: signal => request('/api/health', { signal, validate: v => typeof v?.codex_installed === 'boolean' }),
    listCases: signal => request('/api/cases', { signal, validate: v => Array.isArray(v) && v.every(c => ID.test(c.id) && typeof c.title === 'string') }),
    createCase: data => request('/api/cases', { body: data, validate: isCase }),
    getCase: (id, signal) => request(`/api/cases/${identifier(id)}`, { signal, validate: isCase }),
    freeze: (id, revision, text) => request(`/api/cases/${identifier(id)}/freeze`, { body: { revision, text }, validate: isCase }),
    clarify: (id, text, source) => request(`/api/cases/${identifier(id)}/clarifications`, { body: { text, source }, validate: isCase }),
    preview: record => request(`/api/cases/${identifier(record.id)}/prompt-preview`, { body: record.draft, validate: v => typeof v?.description === 'string' && typeof v.over_limit === 'boolean' }),
    submitGeneration: data => request('/api/generate', { body: data, validate: isJob }),
    getGenerationStatus: (id, signal) => request(`/api/jobs/${identifier(id)}`, { signal, validate: isJob }),
    getRevision: async (caseId, versionId, signal) => {
      const record = await request(`/api/cases/${identifier(caseId)}`, { signal, validate: isCase })
      const version = record.versions.find(v => v.id === identifier(versionId))
      if (!version) throw new WitnessError(404, 'Saved revision is missing.')
      return version
    },
  }
}
// AggregateX migration: no backend exists yet, so preview mode answers locally (see services/previewBackend.js).
export const witness = createWitnessClient(previewMode ? previewFetch : undefined)
export const imageUrl = version => {
  if (!version || version.image_url !== `/images/${identifier(version.id)}`) throw new WitnessError(502, 'Invalid saved image URL.')
  return BASE + version.image_url
}
export const downloadUrl = (caseId, versionId) => `${BASE}/api/cases/${identifier(caseId)}/versions/${identifier(versionId)}/export.png`
export async function pollJob(client, jobId, { signal, onStatus, interval = 1500, deadline = 660000 } = {}) {
  const started = Date.now()
  while (!signal?.aborted) {
    const job = await client.getGenerationStatus(jobId, signal)
    onStatus?.(job)
    if (job.status !== 'working') return job
    if (Date.now() - started > deadline) throw new WitnessError(408, 'Polling timed out. Reconnect to inspect the existing job; do not submit again.')
    await new Promise((resolve, reject) => {
      const stop = () => { clearTimeout(timer); reject(new DOMException('Polling stopped', 'AbortError')) }
      const timer = setTimeout(() => { signal?.removeEventListener('abort', stop); resolve() }, interval)
      signal?.addEventListener('abort', stop, { once: true })
      if (signal?.aborted) stop()
    })
  }
  throw new DOMException('Polling stopped', 'AbortError')
}
