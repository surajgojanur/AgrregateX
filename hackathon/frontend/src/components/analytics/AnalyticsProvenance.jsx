import { ANALYTICS_FAMILIES, describePanelSource, freshnessTimestamp } from '../../lib/analyticsProvenance'

const MODE_LABELS = { raw_source: 'Direct source queries', rollup: 'Incremental rollups' }
const formatTime = (value) => {
  const date = new Date(value)
  return Number.isFinite(date.getTime()) ? date.toLocaleTimeString() : null
}
export function PanelSourceBadge({ family, panel }) {
  const source = panel?.source
  const mode = source?.status === 'verified' ? source.mode : 'unknown'
  const label = mode === 'raw_source' ? 'Direct source' : mode === 'rollup' ? 'Rollup' : 'Not verified'
  const aria = `${family}: ${MODE_LABELS[mode] || 'data source not verified'}`
  return <span className={`ax-source-badge ax-source-badge--${mode}`} aria-label={aria}>{label}</span>
}

export function DataSourceIndicator({ classification, panels }) {
  const mode = classification?.mode || 'unknown'
  const label = MODE_LABELS[mode] || classification?.label || 'Data source not verified'
  let description = 'Source metadata is missing, malformed, or unsupported. No mode is assumed.'
  if (classification?.status === 'uniform' && mode === 'raw_source') {
    const source = panels?.summary?.source
    const interval = source?.status === 'verified' ? source.ranges.edges[0] : null
    const window = interval
      ? ` Requested interval [${new Date(interval.start).toISOString()}, ${new Date(interval.end).toISOString()}) UTC.`
      : ''
    description = `Each analytics response queried authoritative source rows directly. Maintained stream tables were not used; the four HTTP responses have independent SQL statement snapshots.${window}`
  } else if (classification?.status === 'uniform' && mode === 'rollup') {
    description = 'Each response reports incremental rollups for complete UTC buckets and source-row queries for partial edges. A recent refresh does not establish aggregate correctness or exact commit-to-visible delay.'
  } else if (classification?.status === 'mixed') {
    description = 'Responses are incomplete, disagree about their mode, or contain contradictory provenance. Per-panel source labels below show what each response reported.'
  }

  const role = classification?.status === 'mixed' ? 'alert' : mode === 'unknown' ? 'status' : 'status'
  return (
    <section className={`ax-source ax-source--${mode}`} aria-label="Analytics data source" role={role} aria-live="polite">
      <div className="ax-source__copy">
        <strong>{label}</strong>
        <span>{description}</span>
      </div>
      <details className="ax-source__details">
        <summary>Per-panel provenance</summary>
        <ul>
          {ANALYTICS_FAMILIES.map(([family, name]) => {
            const panel = panels?.[family]
            const received = formatTime(panel?.receivedAt)
            return <li key={family}>
              <PanelSourceBadge family={name} panel={panel} />
              <span>{describePanelSource(family, panel)}</span>
              {received && <span className="ax-source__received">Response received {received}</span>}
            </li>
          })}
        </ul>
      </details>
    </section>
  )
}

export function QueryFreshness({ classification, summaryPanel }) {
  if (classification?.mode === 'raw_source' && classification.status === 'uniform') {
    const received = formatTime(summaryPanel?.receivedAt)
    return <span className="ax-fresh ax-fresh--source" role="status">
      Source rows visible to each SQL statement{received ? ` · summary response received ${received}` : ''}
    </span>
  }
  if (classification?.mode !== 'rollup' || classification?.status !== 'uniform') {
    return <span className="ax-fresh ax-fresh--warn" role="status">Refresh age not verified for every panel</span>
  }
  const freshness = summaryPanel?.data?.freshness
  const timestamp = freshnessTimestamp(freshness)
  if (timestamp == null) {
    return <span className="ax-fresh ax-fresh--warn" role="status">Last completed stream refresh unavailable</span>
  }
  const text = new Date(timestamp).toLocaleTimeString()
  const healthy = freshness?.healthy === true
  return <span className={`ax-fresh ${healthy ? '' : 'ax-fresh--warn'}`} role="status"
    title="Last completed refresh age is not proof of aggregate correctness or commit-to-visible delay.">
    <span className={`dot ${healthy ? 'dot--ok' : 'dot--warn'}`} /> Last completed stream refresh at {text}
  </span>
}
