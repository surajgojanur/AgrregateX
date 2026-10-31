import test from 'node:test'
import assert from 'node:assert/strict'
import { createWitnessClient, imageUrl, pollJob } from '../../src/api/witnesstrace.js'
const id = 'a'.repeat(32)
const reply = (v, status = 200) => new Response(JSON.stringify(v), { status })
test('real paths, payload and job validation', async () => {
  const client = createWitnessClient(async (url, options) => {
    assert.equal(url, '/wt-api/api/generate')
    assert.equal(JSON.parse(options.body).case_id, id)
    return reply({ job_id: id, status: 'working', image_url: null })
  })
  assert.equal((await client.submitGeneration({ case_id: id })).status, 'working')
})
test('case list validates bare arrays and identifiers', async () => {
  assert.deepEqual(await createWitnessClient(async () => reply([{ id, title: 'Synthetic' }])).listCases(), [{ id, title: 'Synthetic' }])
  await assert.rejects(createWitnessClient(async () => reply({ cases: [] })).listCases(), /Unexpected/)
  await assert.rejects(async () => createWitnessClient().getCase('../private'), /Invalid record/)
})
test('validation errors, session expiry and malformed response', async () => {
  await assert.rejects(createWitnessClient(async () => reply({ detail: [{ msg: 'Too short' }] }, 422)).health(), /Too short/)
  await assert.rejects(createWitnessClient(async () => reply({}, 401)).health(), /Session expired/)
  await assert.rejects(createWitnessClient(async () => new Response('bad')).health(), /Invalid response/)
})
test('network error and timeout do not resubmit', async () => {
  let calls = 0
  await assert.rejects(createWitnessClient(async () => { calls++; throw new Error('offline') }).health(), /connection lost/)
  assert.equal(calls, 1)
  const slow = createWitnessClient((_, { signal }) => new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('cancel', 'AbortError')))), 5)
  await assert.rejects(slow.health(), /timed out/)
})
test('request cancellation and poll cancellation never submit', async () => {
  const controller = new AbortController(); controller.abort()
  await assert.rejects(pollJob({}, id, { signal: controller.signal }), { name: 'AbortError' })
  const client = createWitnessClient(async (_, { signal }) => { if (signal.aborted) throw new DOMException('cancel', 'AbortError') })
  await assert.rejects(client.health(controller.signal), { name: 'AbortError' })
})
test('poll genuine lifecycle, failure and deadline', async () => {
  const states = ['working', 'complete']; const seen = []
  const client = { getGenerationStatus: async () => ({ job_id: id, status: states.shift() }) }
  assert.equal((await pollJob(client, id, { interval: 1, onStatus: j => seen.push(j.status) })).status, 'complete')
  assert.deepEqual(seen, ['working', 'complete'])
  assert.equal((await pollJob({ getGenerationStatus: async () => ({ status: 'failed' }) }, id)).status, 'failed')
  await assert.rejects(pollJob({ getGenerationStatus: async () => ({ status: 'working' }) }, id, { deadline: -1 }), /Polling timed out/)
})
test('complete requires canonical image and URL rejects external origins', async () => {
  await assert.rejects(createWitnessClient(async () => reply({ job_id: id, status: 'complete', image_url: 'https://bad.test/p.png' })).submitGeneration({}), /Unexpected/)
  assert.equal(imageUrl({ id, image_url: `/images/${id}` }), `/wt-api/images/${id}`)
  assert.throws(() => imageUrl({ id, image_url: 'https://bad.test' }), /Invalid saved image/)
})
