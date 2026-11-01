import test from 'node:test'
import assert from 'node:assert/strict'
import {
  ANALYTICS_FAMILIES,
  classifyAnalyticsSet,
  dashboardQueryKey,
  freshnessAgeSeconds,
  normalizeAnalyticsResponse,
} from '../../src/lib/analyticsProvenance.js'

const interval = { from: '2026-10-01T00:00:00.000Z', to: '2026-10-08T00:00:00.000Z' }
const rawTables = {
  summary: ['ax.orders'],
  trends: ['ax.orders'],
  products: ['ax.orders', 'ax.products'],
  breakdown: ['ax.orders'],
}

function response(family, mode = 'raw_source') {
  const base = {
    ...interval,
    analytics_mode: mode,
    provenance: {
      source_tables: rawTables[family],
      uses_stream_tables: mode === 'rollup',
      consistency: 'single_sql_statement_snapshot',
      consistency_scope: 'per_http_response_only',
    },
    source: { stream_table_range: null, raw_edge_ranges: [[interval.from, interval.to]] },
    freshness: null,
  }
  if (family === 'trends') base.grain = 'day'
  if (family === 'breakdown') base.by = 'status'
  if (mode === 'rollup') {
    base.provenance.source_tables = {
      summary: ['ax.st_day_product_status', 'ax.orders'],
      trends: ['ax.st_day_category_status', 'ax.orders'],
      products: ['ax.st_day_product_status', 'ax.orders', 'ax.products'],
      breakdown: ['ax.st_day_product_status', 'ax.orders'],
    }[family]
    base.source = { stream_table_range: [interval.from, interval.to], raw_edge_ranges: [] }
    base.freshness = { verified_at: '2026-10-08T00:00:00Z', healthy: true }
  }
  return base
}

function panelsFor(mode = 'raw_source') {
  return Object.fromEntries(ANALYTICS_FAMILIES.map(([family]) => [family, {
    status: 'success', source: normalizeAnalyticsResponse(family, response(family, mode), { requestedRange: interval }),
  }]))
}

test('valid raw-source response identifies source rows and statement scope', () => {
  const source = normalizeAnalyticsResponse('summary', response('summary'), { requestedRange: interval })
  assert.equal(source.status, 'verified')
  assert.equal(source.mode, 'raw_source')
  assert.deepEqual(source.sourceTables, ['ax.orders'])
  assert.equal(source.freshness, null)
})

test('valid rollup with complete buckets and partial edges is classified', () => {
  const value = response('summary', 'rollup')
  value.source.raw_edge_ranges = [[interval.from, '2026-10-02T00:00:00Z'], ['2026-10-07T00:00:00Z', interval.to]]
  value.source.stream_table_range = ['2026-10-02T00:00:00Z', '2026-10-07T00:00:00Z']
  const source = normalizeAnalyticsResponse('summary', value, { requestedRange: interval })
  assert.equal(source.status, 'verified')
  assert.deepEqual(source.ranges.edges, [
    { start: Date.parse(interval.from), end: Date.parse('2026-10-02T00:00:00Z') },
    { start: Date.parse('2026-10-07T00:00:00Z'), end: Date.parse(interval.to) },
  ])
  assert.equal(source.ranges.stream.start, Date.parse('2026-10-02T00:00:00Z'))
})

test('rollup with no complete buckets and raw full-interval edges is valid', () => {
  const value = response('summary', 'rollup')
  value.source = { stream_table_range: null, raw_edge_ranges: [[interval.from, interval.to]] }
  const source = normalizeAnalyticsResponse('summary', value, { requestedRange: interval })
  assert.equal(source.status, 'verified')
  assert.equal(source.ranges.stream, null)
})

test('missing/unknown modes and missing provenance are never assumed to be rollups', () => {
  assert.equal(normalizeAnalyticsResponse('summary', {}).status, 'unknown')
  assert.equal(normalizeAnalyticsResponse('summary', { ...response('summary'), analytics_mode: 'future' }).status, 'unknown')
  const noProvenance = response('summary'); delete noProvenance.provenance
  assert.equal(normalizeAnalyticsResponse('summary', noProvenance).status, 'unknown')
})

test('mode contradictions and wrong per-family source tables are rejected', () => {
  const conflict = response('summary'); conflict.provenance.uses_stream_tables = true
  assert.equal(normalizeAnalyticsResponse('summary', conflict).status, 'contradictory')
  const wrongFamily = response('products')
  assert.equal(normalizeAnalyticsResponse('summary', wrongFamily).status, 'contradictory')
})

test('raw-source requires null freshness and exact full request edge', () => {
  const freshness = response('summary'); freshness.freshness = { healthy: true }
  assert.equal(normalizeAnalyticsResponse('summary', freshness).status, 'contradictory')
  const wrongEdge = response('summary'); wrongEdge.source.raw_edge_ranges = []
  assert.equal(normalizeAnalyticsResponse('summary', wrongEdge).status, 'unknown')
})

test('malformed ranges and stale request intervals are not verified', () => {
  const malformed = response('summary'); malformed.source.raw_edge_ranges = [['bad', interval.to]]
  assert.equal(normalizeAnalyticsResponse('summary', malformed).status, 'unknown')
  const gap = response('summary', 'rollup')
  gap.source.stream_table_range = ['2026-10-02T00:00:00Z', '2026-10-07T00:00:00Z']
  gap.source.raw_edge_ranges = [[interval.from, '2026-10-01T12:00:00Z'], ['2026-10-07T00:00:00Z', interval.to]]
  assert.equal(normalizeAnalyticsResponse('summary', gap).status, 'unknown')
  assert.equal(normalizeAnalyticsResponse('summary', response('summary'), {
    requestedRange: { from: interval.from, to: '2026-10-09T00:00:00Z' },
  }).status, 'unknown')
})

test('all endpoint families can agree on raw or rollup mode', () => {
  assert.deepEqual(classifyAnalyticsSet(panelsFor()), {
    status: 'uniform', mode: 'raw_source', label: 'Direct source queries',
  })
  assert.equal(classifyAnalyticsSet(panelsFor('rollup')).mode, 'rollup')
})

test('mixed, missing and legacy response sets are not labelled uniformly', () => {
  const mixed = panelsFor()
  mixed.products.source = normalizeAnalyticsResponse('products', response('products', 'rollup'), { requestedRange: interval })
  assert.equal(classifyAnalyticsSet(mixed).status, 'mixed')
  delete mixed.breakdown.source
  assert.equal(classifyAnalyticsSet(mixed).status, 'mixed')
  const legacy = Object.fromEntries(ANALYTICS_FAMILIES.map(([key]) => [key, { status: 'success', source: { status: 'unknown' } }]))
  assert.deepEqual(classifyAnalyticsSet(legacy), { status: 'unknown', mode: 'unknown', label: 'Data source not verified' })
})

test('freshness tolerates null/malformed values and clamps future timestamps', () => {
  assert.equal(freshnessAgeSeconds(null), null)
  assert.equal(freshnessAgeSeconds({ verified_at: 'not-a-date' }), null)
  assert.equal(freshnessAgeSeconds({ verified_at: '2026-10-08T00:00:00Z' }, Date.parse('2026-10-07T00:00:00Z')), 0)
})

test('tenant and filter changes produce different request generations', () => {
  const base = { tenant: 2, range: interval, grain: 'day', by: 'category' }
  assert.notEqual(dashboardQueryKey(base), dashboardQueryKey({ ...base, tenant: 3 }))
  assert.notEqual(dashboardQueryKey(base), dashboardQueryKey({ ...base, range: { ...interval, to: '2026-10-09T00:00:00Z' } }))
  assert.notEqual(dashboardQueryKey(base), dashboardQueryKey({ ...base, by: 'status' }))
})
