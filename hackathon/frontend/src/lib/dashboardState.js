import { normalizeAnalyticsResponse } from './analyticsProvenance.js'

const PAYLOADS = {
  summary: (response) => isRecord(response.summary) &&
    ['orders', 'sale_orders', 'units_sold', 'sales_cents', 'avg_order_cents', 'cancelled_or_refunded', 'cancel_rate']
      .every((key) => finite(response.summary[key])) && isRecord(response.summary.by_status),
  trends: (response) => Array.isArray(response.points) && response.points.every((point) =>
    isRecord(point) && validTimestamp(point.bucket) &&
    finite(point.orders) && finite(point.sales_cents) && finite(point.cancelled_or_refunded)),
  products: (response) => Array.isArray(response.products) && response.products.every((product) =>
    isRecord(product) && finite(product.product_id) && finite(product.rank) &&
    finite(product.units_sold) && finite(product.sales_cents)),
  breakdown: (response) => Array.isArray(response.rows) && response.rows.every((row) =>
    isRecord(row) && (typeof row.key === 'string' || finite(row.key) || row.key === null) &&
    finite(row[response.by === 'status' ? 'gross_cents' : 'sales_cents'])),
}

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

function validTimestamp(value) {
  return typeof value === 'string' && Number.isFinite(Date.parse(value))
}
export function createLoadingPanel() {
  return { status: 'loading', source: { status: 'unknown', mode: 'unknown', reason: 'Awaiting an analytics response.' } }
}

export function createLoadingPanels(previousPanels = null) {
  return Object.fromEntries(Object.keys(PAYLOADS).map((family) => {
    const previous = previousPanels?.[family]
    return [family, previous?.status === 'success' ? previous : createLoadingPanel()]
  }))
}

export function buildPanelResult(family, settled, context) {
  if (settled.status === 'rejected') {
    const error = settled.reason
    return {
      status: 'error',
      error: typeof error?.message === 'string' ? error.message : 'Unknown request failure.',
      unavailable: error?.status === 503 ? error?.data?.shard || '?' : null,
      statusCode: Number.isInteger(error?.status) ? error.status : null,
      source: { status: 'unknown', mode: 'unknown', reason: 'This panel did not return a response.' },
    }
  }

  const { data, ms, receivedAt } = settled.value
  if (!isRecord(data) || !PAYLOADS[family]?.(data)) {
    return {
      status: 'error',
      error: 'The API response is missing this panel’s expected data fields.',
      unavailable: null,
      statusCode: null,
      source: normalizeAnalyticsResponse(family, data, context),
    }
  }
  const source = normalizeAnalyticsResponse(family, data, context)
  if (source.status === 'contradictory') {
    return {
      status: 'error',
      error: source.reason || 'The API response metadata conflicts with the current dashboard request.',
      unavailable: null,
      statusCode: null,
      source,
    }
  }
  return {
    status: 'success',
    data,
    ms: typeof ms === 'number' && Number.isFinite(ms) ? ms : null,
    receivedAt: typeof receivedAt === 'string' && Number.isFinite(Date.parse(receivedAt)) ? receivedAt : null,
    source,
  }
}

export function buildDashboardResults(settledByFamily, context) {
  return Object.fromEntries(Object.entries(settledByFamily).map(([family, settled]) => [
    family,
    buildPanelResult(family, settled, context),
  ]))
}
