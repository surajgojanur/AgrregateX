import test from 'node:test'
import assert from 'node:assert/strict'
import { query } from '../../src/api/client.js'
import { safeNext } from '../../src/lib/auth.js'
import { relativeTime } from '../../src/lib/format.js'

test('query() builds a query string and skips empty values', () => {
  assert.equal(query({ from: '2026-10-01T00:00:00Z', to: '', grain: 'day', shard: null }), '?from=2026-10-01T00%3A00%3A00Z&grain=day')
  assert.equal(query({}), '')
  assert.equal(query(), '')
})

test('safeNext() only allows dashboard paths (no open redirect)', () => {
  assert.equal(safeNext('/app#/dashboard'), '/app#/dashboard')
  assert.equal(safeNext('/app'), '/app')
  for (const bad of ['https://evil.example/app', '//evil.example', '/application', '/login', null, 42]) {
    assert.equal(safeNext(bad), '/app', String(bad))
  }
})

test('relativeTime() formats recent timestamps', () => {
  const now = Date.parse('2026-10-31T12:00:00Z')
  assert.equal(relativeTime('2026-10-31T11:59:40Z', now), 'just now')
  assert.equal(relativeTime('2026-10-31T11:50:00Z', now), '10 min ago')
  assert.equal(relativeTime('2026-10-31T09:00:00Z', now), '3 h ago')
  assert.equal(relativeTime(null, now), '')
})
