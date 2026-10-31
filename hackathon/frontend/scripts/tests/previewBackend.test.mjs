import test from 'node:test'
import assert from 'node:assert/strict'
import { NO_BACKEND, PREVIEW_USER, previewFetch, previewMode } from '../../src/services/previewBackend.js'
import { witness } from '../../src/api/witnesstrace.js'

test('preview mode is on unless a backend is explicitly enabled', () => {
  assert.equal(previewMode, true)
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
test('the default WitnessTrace client never reaches the network in preview mode', async (t) => {
  t.mock.method(globalThis, 'fetch', () => { throw new Error('network call attempted') })
  await assert.rejects(witness.health(), (e) => e.status === 503 && e.message === NO_BACKEND)
  await assert.rejects(witness.listCases(), (e) => e.status === 503)
  assert.equal(globalThis.fetch.mock.callCount(), 0)
})
