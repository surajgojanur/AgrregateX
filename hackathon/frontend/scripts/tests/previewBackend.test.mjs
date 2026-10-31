import test from 'node:test'
import assert from 'node:assert/strict'
import { NO_BACKEND, PREVIEW_USER, previewFetch, previewMode } from '../../src/services/previewBackend.js'
import { witnessMode } from '../../src/api/witnesstrace.js'

test('the AgrregateX API is used by default; preview mode is opt-in (VITE_BACKEND_ENABLED=0)', () => {
  assert.equal(previewMode, false)
})
test('only the session check answers; it returns the labelled preview user', async () => {
  const me = await previewFetch('/api/auth/me')
  assert.equal(me.status, 200)
  assert.deepEqual(await me.json(), { user: { ...PREVIEW_USER } })
  assert.equal(PREVIEW_USER.preview, true)
})
test('every other call fails with 503 and no data', async () => {
  for (const [url, method] of [['/api/health'], ['/api/stats'], ['/api/auth/login', 'POST'], ['/wt-api/api/cases'], ['/api/auth/me', 'POST']]) {
    const res = await previewFetch(url, { method })
    assert.equal(res.status, 503, url)
    assert.deepEqual(await res.json(), { detail: NO_BACKEND, preview: true })
  }
})
test('the legacy WitnessTrace client is off unless VITE_WITNESSTRACE_LOCAL=1', () => {
  assert.equal(witnessMode, false)
})
