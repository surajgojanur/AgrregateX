import { normalizeAnalyticsResponse } from './analyticsProvenance.js'

const PAYLOADS = {
  summary: (response) => response.summary && typeof response.summary === 'object',
  trends: (response) => Array.isArray(response.points),
  products: (response) => Array.isArray(response.products),
  breakdown: (response) => Array.isArray(response.rows),
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

export function buildPanelResult(family, settled, { requestedRange }) {
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
  if (!data || typeof data !== 'object' || !PAYLOADS[family]?.(data)) {
    return {
      status: 'error',
      error: 'The API response is missing this panel’s expected data fields.',
      unavailable: null,
      statusCode: null,
      source: normalizeAnalyticsResponse(family, data, { requestedRange }),
    }
  }
  return {
    status: 'success',
    data,
    ms: typeof ms === 'number' && Number.isFinite(ms) ? ms : null,
    receivedAt: typeof receivedAt === 'string' && Number.isFinite(Date.parse(receivedAt)) ? receivedAt : null,
    source: normalizeAnalyticsResponse(family, data, { requestedRange }),
  }
}

export function buildDashboardResults(settledByFamily, context) {
  return Object.fromEntries(Object.entries(settledByFamily).map(([family, settled]) => [
    family,
    buildPanelResult(family, settled, context),
  ]))
}
