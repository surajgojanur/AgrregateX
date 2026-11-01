export const ANALYTICS_FAMILIES = [
  ['summary', 'Summary'],
  ['trends', 'Trends'],
  ['products', 'Top products'],
  ['breakdown', 'Breakdown'],
]

const EXPECTED_TABLES = {
  raw_source: {
    summary: ['ax.orders'],
    trends: ['ax.orders'],
    products: ['ax.orders', 'ax.products'],
    breakdown_status: ['ax.orders'],
    breakdown_category: ['ax.orders', 'ax.products'],
  },
  rollup: {
    summary: ['ax.st_day_product_status', 'ax.orders'],
    trends_day: ['ax.st_day_category_status', 'ax.orders'],
    trends_hour: ['ax.st_hour_category_status', 'ax.orders'],
    products: ['ax.st_day_product_status', 'ax.orders', 'ax.products'],
    breakdown_status: ['ax.st_day_product_status', 'ax.orders'],
    breakdown_category: ['ax.st_day_category_status', 'ax.orders', 'ax.products'],
  },
}

const parseTime = (value) => typeof value === 'string' ? Date.parse(value) : Number.NaN

function parseRange(value) {
  if (!Array.isArray(value) || value.length !== 2) return null
  const start = parseTime(value[0])
  const end = parseTime(value[1])
  if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) return null
  return { start, end }
}

function sameTables(actual, expected) {
  if (!Array.isArray(actual) || !actual.every((table) => typeof table === 'string')) return false
  if (actual.length !== expected.length || new Set(actual).size !== actual.length) return false
  return [...actual].sort().every((table, index) => table === [...expected].sort()[index])
}

function expectedTablesFor(mode, family, response) {
  if (mode === 'raw_source') {
    if (family === 'breakdown') return EXPECTED_TABLES.raw_source[`breakdown_${response.by}`]
    return EXPECTED_TABLES.raw_source[family]
  }
  if (family === 'trends') return EXPECTED_TABLES.rollup[`trends_${response.grain}`]
  if (family === 'breakdown') return EXPECTED_TABLES.rollup[`breakdown_${response.by}`]
  return EXPECTED_TABLES.rollup[family]
}

function unknown(reason) {
  return { status: 'unknown', mode: 'unknown', reason, sourceTables: [], ranges: null }
}

function contradictory(reason, mode = 'unknown') {
  return { status: 'contradictory', mode, reason, sourceTables: [], ranges: null }
}

/** Validate the provenance contract for one independent analytics HTTP response. */
export function normalizeAnalyticsResponse(family, response, {
  requestedRange,
  requestedTenant,
  requestedGrain,
  requestedBreakdown,
} = {}) {
  if (!response || typeof response !== 'object' || Array.isArray(response)) {
    return unknown('Response or provenance metadata is missing.')
  }
  const { analytics_mode: mode, provenance, source } = response
  if (mode !== 'rollup' && mode !== 'raw_source') {
    return unknown(mode == null ? 'This response has no analytics_mode.' : 'This response reports an unknown analytics mode.')
  }
  if (!provenance || typeof provenance !== 'object' || Array.isArray(provenance)) {
    return unknown('This response has no provenance object.')
  }
  if (provenance.consistency !== 'single_sql_statement_snapshot' ||
      provenance.consistency_scope !== 'per_http_response_only') {
    return unknown('Statement snapshot scope is missing or unsupported.')
  }
  const responseRange = parseRange([response.from, response.to])
  if (!responseRange) return unknown('The response request interval is missing or malformed.')
  if (requestedRange) {
    const requested = parseRange([requestedRange.from, requestedRange.to])
    if (!requested || requested.start !== responseRange.start || requested.end !== responseRange.end) {
      return unknown('The response interval does not match the current dashboard filters.')
    }
  }
  if (requestedTenant != null) {
    if (!Object.hasOwn(response, 'tenant_id')) return unknown('The response tenant ID is missing.')
    if (response.tenant_id !== requestedTenant) {
      return contradictory('The response tenant ID does not match the current dashboard tenant.', mode)
    }
  }
  if (family === 'trends' && requestedGrain != null) {
    if (response.grain == null) return unknown('The response trend grain is missing.')
    if (response.grain !== requestedGrain) {
      return contradictory('The response trend grain does not match the current dashboard grain.', mode)
    }
  }
  if (family === 'breakdown' && requestedBreakdown != null) {
    if (response.by == null) return unknown('The response breakdown selector is missing.')
    if (response.by !== requestedBreakdown) {
      return contradictory('The response breakdown selector does not match the current dashboard filter.', mode)
    }
  }
  if (provenance.uses_stream_tables !== (mode === 'rollup')) {
    return contradictory('analytics_mode conflicts with uses_stream_tables.', mode)
  }
  const expectedTables = expectedTablesFor(mode, family, response)
  if (!expectedTables || !sameTables(provenance.source_tables, expectedTables)) {
    return contradictory('Reported source tables do not match this endpoint family.', mode)
  }
  if (!source || typeof source !== 'object' || Array.isArray(source) ||
      !Array.isArray(source.raw_edge_ranges)) {
    return unknown('Source ranges are missing or malformed.')
  }
  const edges = source.raw_edge_ranges.map(parseRange)
  if (edges.some((range) => range == null)) return unknown('A source edge range is malformed.')

  let streamRange = null
  if (mode === 'raw_source') {
    if (source.stream_table_range !== null) {
      return contradictory('Raw-source response reports a stream-table range.', mode)
    }
    if (!Object.hasOwn(response, 'freshness') || response.freshness !== null) {
      return contradictory('Raw-source response must not report stream freshness.', mode)
    }
    if (edges.length !== 1 ||
        edges[0].start !== responseRange.start || edges[0].end !== responseRange.end) {
      return unknown('Raw-source range does not match the reported request interval.')
    }
  } else {
    if (source.stream_table_range !== null) {
      streamRange = parseRange(source.stream_table_range)
      if (!streamRange) return unknown('The stream-table range is malformed.')
    }
    const segments = [...edges, ...(streamRange ? [streamRange] : [])]
      .sort((left, right) => left.start - right.start)
    if (!segments.length || segments[0].start !== responseRange.start ||
        segments[segments.length - 1].end !== responseRange.end ||
        segments.some((segment) => segment.start < responseRange.start || segment.end > responseRange.end) ||
        segments.some((segment, index) => index > 0 && segments[index - 1].end !== segment.start)) {
      return unknown('Source ranges do not partition the requested interval exactly.')
    }
  }

  return {
    status: 'verified',
    mode,
    reason: null,
    sourceTables: [...provenance.source_tables],
    ranges: { stream: streamRange, edges },
    responseFrom: response.from,
    responseTo: response.to,
    freshness: mode === 'rollup' ? response.freshness ?? null : null,
    grain: response.grain ?? null,
    breakdownBy: response.by ?? null,
  }
}

/** Never calls a partial or contradictory four-endpoint set uniformly sourced. */
export function classifyAnalyticsSet(panels) {
  const responses = ANALYTICS_FAMILIES.map(([key]) => panels?.[key])
  const sources = responses.map((panel) => panel?.source)
  const complete = responses.every((panel) => panel?.status === 'success') &&
    sources.every((source) => source?.status === 'verified' &&
      (source.mode === 'raw_source' || source.mode === 'rollup'))
  const modes = new Set(sources.filter((source) => source?.status === 'verified').map((source) => source.mode))
  if (complete && modes.size === 1) {
    const mode = [...modes][0]
    return { status: 'uniform', mode, label: mode === 'raw_source' ? 'Direct source queries' : 'Incremental rollups' }
  }
  if (modes.size > 0 || sources.some((source) => source?.status === 'contradictory')) {
    return { status: 'mixed', mode: 'mixed', label: 'Mixed or incomplete sources' }
  }
  return { status: 'unknown', mode: 'unknown', label: 'Data source not verified' }
}

export function describePanelSource(family, panel) {
  const source = panel?.source
  if (panel?.status === 'loading') return `${ANALYTICS_FAMILIES.find(([key]) => key === family)?.[1] || family}: loading.`
  if (panel?.status === 'error') {
    const name = ANALYTICS_FAMILIES.find(([key]) => key === family)?.[1] || family
    const mode = source?.status === 'verified' ? ` Response metadata reports ${source.mode}.` : ''
    return `${name}: unavailable; ${panel.error}.${mode}`
  }
  if (source?.status !== 'verified') {
    return `${ANALYTICS_FAMILIES.find(([key]) => key === family)?.[1] || family}: data source not verified. ${source?.reason || ''}`.trim()
  }
  const name = ANALYTICS_FAMILIES.find(([key]) => key === family)?.[1] || family
  const rangeText = (range) => `[${new Date(range.start).toISOString()}, ${new Date(range.end).toISOString()}) UTC`
  if (source.mode === 'raw_source') {
    const tables = source.sourceTables.join(' and ')
    const [requested] = source.ranges.edges
    return `${name}: direct source query from ${tables}; no maintained stream tables. Requested interval ${rangeText(requested)}. This response has its own SQL statement snapshot.`
  }
  const tables = source.sourceTables.filter((table) => table.startsWith('ax.st_')).join(' and ')
  const coverage = source.ranges.stream
    ? `complete UTC buckets from ${tables} ${rangeText(source.ranges.stream)}; ${source.ranges.edges.length} partial source edge${source.ranges.edges.length === 1 ? '' : 's'}${source.ranges.edges.length ? ` ${source.ranges.edges.map(rangeText).join(', ')}` : ''}`
    : `source rows for the full interval ${rangeText(source.ranges.edges[0])}; no complete stream-table bucket`
  return `${name}: ${coverage}. Refresh recency does not prove aggregate correctness or commit-to-visible delay.`
}

export function freshnessTimestamp(freshness) {
  if (!freshness || typeof freshness !== 'object' || Array.isArray(freshness)) return null
  const time = parseTime(freshness.verified_at)
  return Number.isFinite(time) ? time : null
}

export function freshnessAgeSeconds(freshness, now = Date.now()) {
  const timestamp = freshnessTimestamp(freshness)
  if (timestamp == null || typeof now !== 'number' || !Number.isFinite(now)) return null
  return Math.max(0, Math.floor((now - timestamp) / 1000))
}

export function dashboardQueryKey({ tenant, range, grain, by }) {
  return JSON.stringify([tenant, range?.from, range?.to, grain, by])
}
