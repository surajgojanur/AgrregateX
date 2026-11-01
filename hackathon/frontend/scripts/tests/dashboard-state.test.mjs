import test from 'node:test'
import assert from 'node:assert/strict'
import { buildDashboardResults, createLoadingPanels } from '../../src/lib/dashboardState.js'
import { createDashboardRequestGate } from '../../src/lib/dashboardRequestGate.js'
import { classifyAnalyticsSet, dashboardQueryKey } from '../../src/lib/analyticsProvenance.js'

const range = { from: '2026-10-01T00:00:00Z', to: '2026-10-08T00:00:00Z' }
const sourceResponse = (family) => ({
  from: range.from,
  to: range.to,
  tenant_id: 2,
  analytics_mode: 'raw_source',
  provenance: {
    source_tables: family === 'products' ? ['ax.orders', 'ax.products'] : ['ax.orders'],
    uses_stream_tables: false,
    consistency: 'single_sql_statement_snapshot',
    consistency_scope: 'per_http_response_only',
  },
  source: { stream_table_range: null, raw_edge_ranges: [[range.from, range.to]] },
  freshness: null,
  ...(family === 'summary' ? { summary: { orders: 1, sale_orders: 1, units_sold: 2, sales_cents: 2998,
    avg_order_cents: 2998, cancelled_or_refunded: 0, cancel_rate: 0, by_status: { paid: { orders: 1 } } } } : {}),
  ...(family === 'trends' ? { points: [] } : {}),
  ...(family === 'products' ? { products: [] } : {}),
  ...(family === 'breakdown' ? { rows: [], by: 'status' } : {}),
})
const success = (family) => ({ status: 'fulfilled', value: { data: sourceResponse(family), ms: 12, receivedAt: range.to } })

test('one failed endpoint clears only its own prior panel and records 503', () => {
  const first = Object.fromEntries(['summary', 'trends', 'products', 'breakdown'].map((family) => [family, success(family)]))
  const prior = buildDashboardResults(first, { requestedRange: range })
  assert.equal(prior.summary.status, 'success')
  const next = Object.fromEntries(['summary', 'trends', 'products', 'breakdown'].map((family) => [family, success(family)]))
  next.products = { status: 'rejected', reason: Object.assign(new Error('shard unavailable'), { status: 503, data: { shard: 'B' } }) }
  const updated = buildDashboardResults(next, { requestedRange: range })
  assert.equal(updated.summary.status, 'success')
  assert.equal(updated.products.status, 'error')
  assert.equal(updated.products.unavailable, 'B')
  assert.equal(updated.products.statusCode, 503)
  assert.match(updated.products.error, /shard unavailable/)
})

test('malformed successful payload is an explicit error without rendering data', () => {
  const panels = buildDashboardResults({
    summary: { status: 'fulfilled', value: { data: { ...sourceResponse('summary'), summary: null } } },
  }, { requestedRange: range })
  assert.equal(panels.summary.status, 'error')
  assert.equal(panels.summary.source.status, 'verified')
  assert.equal(panels.summary.data, undefined)
})

test('malformed entries in analytics collections are rejected before panel rendering', () => {
  const cases = [
    ['trends', { points: [null] }],
    ['products', { products: [null] }],
    ['breakdown', { rows: [null], by: 'status' }],
    ['summary', { summary: [] }],
    ['summary', { summary: { orders: 1, sale_orders: 1, units_sold: 2, avg_order_cents: 2,
      cancelled_or_refunded: 0, cancel_rate: 0, by_status: {} } }],
  ]
  for (const [family, payload] of cases) {
    const panel = buildDashboardResults({
      [family]: { status: 'fulfilled', value: { data: { ...sourceResponse(family), ...payload } } },
    }, { requestedRange: range })[family]
    assert.equal(panel.status, 'error', `${family} malformed payload must not reach a renderer`)
    assert.equal(panel.data, undefined)
  }
})

test('contradictory tenant metadata prevents rendering response data', () => {
  const data = { ...sourceResponse('summary'), tenant_id: 3 }
  const panel = buildDashboardResults({
    summary: { status: 'fulfilled', value: { data, ms: 1, receivedAt: range.to } },
  }, { requestedRange: range, requestedTenant: 2 }).summary
  assert.equal(panel.status, 'error')
  assert.equal(panel.data, undefined)
  assert.equal(panel.source.status, 'contradictory')
})

test('three raw successes plus malformed summary with valid provenance are not uniform', () => {
  const settled = Object.fromEntries(['summary', 'trends', 'products', 'breakdown'].map((family) => [family, success(family)]))
  settled.summary = {
    status: 'fulfilled',
    value: { data: { ...sourceResponse('summary'), summary: null }, ms: 5, receivedAt: range.to },
  }
  const panels = buildDashboardResults(settled, { requestedRange: range })
  assert.equal(panels.summary.status, 'error')
  assert.equal(panels.summary.source.status, 'verified')
  assert.equal(classifyAnalyticsSet(panels).status, 'mixed')
})

test('loading states do not retain values across a tenant or range key change', () => {
  const oldKey = dashboardQueryKey({ tenant: 2, range, grain: 'day', by: 'category' })
  const newKey = dashboardQueryKey({ tenant: 3, range, grain: 'day', by: 'category' })
  const previous = buildDashboardResults(Object.fromEntries(['summary', 'trends', 'products', 'breakdown'].map((family) => [family, success(family)])), { requestedRange: range })
  assert.equal(createLoadingPanels(previous).summary.status, 'success')
  assert.notEqual(oldKey, newKey)
  const newTenantVisibleState = { requestKey: newKey, panels: createLoadingPanels() }
  assert.equal(newTenantVisibleState.panels.summary.status, 'loading')
})

test('superseded tenant/range requests are aborted and late responses are ignored', () => {
  const gate = createDashboardRequestGate()
  const old = gate.begin('tenant-2-range-a')
  assert.ok(old)
  const current = gate.begin('tenant-3-range-b')
  assert.equal(old.controller.signal.aborted, true)
  assert.equal(gate.isCurrent(old), false)
  assert.equal(gate.isCurrent(current), true)
  assert.equal(gate.finish(current), true)
  assert.equal(gate.isCurrent(current), false)
})

test('same-key automatic refresh cannot overlap, and cleanup cancels in-flight work', () => {
  const gate = createDashboardRequestGate()
  const first = gate.begin('same-query')
  assert.equal(gate.begin('same-query'), null)
  assert.equal(gate.cancel('same-query'), true)
  assert.equal(first.controller.signal.aborted, true)
  assert.equal(gate.pending, false)
})
