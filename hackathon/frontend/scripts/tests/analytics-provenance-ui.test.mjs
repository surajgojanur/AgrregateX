import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { normalizeAnalyticsResponse, ANALYTICS_FAMILIES, classifyAnalyticsSet } from '../../src/lib/analyticsProvenance.js'

const range = { from: '2026-10-01T00:00:00Z', to: '2026-10-08T00:00:00Z' }

function response(family, mode = 'raw_source') {
  const tables = mode === 'raw_source'
    ? (family === 'products' ? ['ax.orders', 'ax.products'] : ['ax.orders'])
    : ({ summary: ['ax.st_day_product_status', 'ax.orders'], trends: ['ax.st_day_category_status', 'ax.orders'],
      products: ['ax.st_day_product_status', 'ax.orders', 'ax.products'], breakdown: ['ax.st_day_product_status', 'ax.orders'] })[family]
  return {
    ...range, analytics_mode: mode, by: 'status', grain: 'day',
    provenance: { source_tables: tables, uses_stream_tables: mode === 'rollup', consistency: 'single_sql_statement_snapshot', consistency_scope: 'per_http_response_only' },
    source: { stream_table_range: mode === 'raw_source' ? null : [range.from, range.to], raw_edge_ranges: mode === 'raw_source' ? [[range.from, range.to]] : [] },
    freshness: mode === 'raw_source' ? null : { verified_at: range.to, healthy: true },
  }
}

let vite
let components
test('accessible source and freshness UI labels reflect verified, mixed and unknown responses', async (t) => {
  vite = await createServer({ configFile: './vite.config.js', server: { middlewareMode: true }, appType: 'custom', logLevel: 'error' })
  t.after(async () => { await vite?.close() })
  components = await vite.ssrLoadModule('/src/components/analytics/AnalyticsProvenance.jsx')

  const panels = Object.fromEntries(ANALYTICS_FAMILIES.map(([family]) => [family, {
    status: 'success', receivedAt: range.to, data: { freshness: null },
    source: normalizeAnalyticsResponse(family, response(family), { requestedRange: range }),
  }]))
  const raw = classifyAnalyticsSet(panels)
  const rawMarkup = renderToStaticMarkup(React.createElement(components.DataSourceIndicator, { classification: raw, panels }))
  assert.match(rawMarkup, /role="status"/)
  assert.match(rawMarkup, /Direct source queries/)
  assert.match(rawMarkup, /authoritative source rows directly/)
  assert.match(rawMarkup, /Requested interval \[2026-10-01T00:00:00.000Z, 2026-10-08T00:00:00.000Z\) UTC/)
  assert.match(rawMarkup, /Summary: Direct source queries/)
  const rawFreshness = renderToStaticMarkup(React.createElement(components.QueryFreshness, { classification: raw, summaryPanel: panels.summary }))
  assert.match(rawFreshness, /Source rows visible to each SQL statement/)
  assert.doesNotMatch(rawFreshness, /Updated .* ago/)

  const rollupPanels = Object.fromEntries(ANALYTICS_FAMILIES.map(([family]) => [family, {
    status: 'success', data: { freshness: response(family, 'rollup').freshness },
    source: normalizeAnalyticsResponse(family, response(family, 'rollup'), { requestedRange: range }),
  }]))
  const rollupFreshness = renderToStaticMarkup(React.createElement(components.QueryFreshness, {
    classification: classifyAnalyticsSet(rollupPanels), summaryPanel: rollupPanels.summary,
  }))
  assert.match(rollupFreshness, /Last completed stream refresh at/)
  assert.match(rollupFreshness, /not proof of aggregate correctness/)

  panels.products.source = normalizeAnalyticsResponse('products', response('products', 'rollup'), { requestedRange: range })
  const mixed = classifyAnalyticsSet(panels)
  const mixedMarkup = renderToStaticMarkup(React.createElement(components.DataSourceIndicator, { classification: mixed, panels }))
  assert.match(mixedMarkup, /role="alert"/)
  assert.match(mixedMarkup, /Mixed or incomplete sources/)
  assert.match(mixedMarkup, /Top products: Incremental rollups/)

  const unknownPanels = Object.fromEntries(ANALYTICS_FAMILIES.map(([family]) => [family, { status: 'success', source: { status: 'unknown' } }]))
  const unknown = classifyAnalyticsSet(unknownPanels)
  const unknownMarkup = renderToStaticMarkup(React.createElement(components.DataSourceIndicator, { classification: unknown, panels: unknownPanels }))
  assert.match(unknownMarkup, /Data source not verified/)
  assert.match(unknownMarkup, /data source not verified/)
  const unknownFreshness = renderToStaticMarkup(React.createElement(components.QueryFreshness, { classification: unknown, summaryPanel: null }))
  assert.match(unknownFreshness, /Refresh age not verified for every panel/)
})
