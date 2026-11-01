import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import Icon from '../components/ui/Icon'
import { DataSourceIndicator, PanelSourceBadge, QueryFreshness } from '../components/analytics/AnalyticsProvenance'
import ConfigMetrics from '../components/analytics/ConfigMetrics'
import { ANALYTICS_FAMILIES, classifyAnalyticsSet, dashboardQueryKey } from '../lib/analyticsProvenance'
import { createDashboardRequestGate } from '../lib/dashboardRequestGate'
import { buildDashboardResults, createLoadingPanels } from '../lib/dashboardState'
import { useApp } from '../state/AppContext'

const money = (cents) =>
  new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format((cents || 0) / 100)
const num = (n) => new Intl.NumberFormat().format(n || 0)
const pct = (x) => `${((x || 0) * 100).toFixed(1)}%`

const PRESETS = [
  { id: '24h', label: '24 h', ms: 24 * 3600e3, grain: 'hour' },
  { id: '7d', label: '7 d', ms: 7 * 86400e3, grain: 'day' },
  { id: '30d', label: '30 d', ms: 30 * 86400e3, grain: 'day' },
  { id: '90d', label: '90 d', ms: 90 * 86400e3, grain: 'day' },
]

// Times the HTTP round trip so every panel shows its measured latency.
async function timed(fn) {
  const t0 = performance.now()
  const data = await fn()
  return { data, ms: Math.round(performance.now() - t0), receivedAt: new Date().toISOString() }
}

function Ms({ panel }) {
  if (panel?.status !== 'success') return null
  const receivedAt = new Date(panel.receivedAt)
  const receivedText = Number.isFinite(receivedAt.getTime()) ? receivedAt.toLocaleTimeString() : 'unknown time'
  return <span className="mono faint ax-ms" title={`HTTP round trip from this browser; response received ${receivedText}`}>
    {panel.ms} ms · {receivedText}
  </span>
}

function PanelContent({ panel, h, children }) {
  if (panel?.status === 'success') return children
  if (panel?.status === 'error') {
    return <p className="alert ax-panel-error" role="alert">
      {panel.unavailable ? `Unavailable: owning shard ${String(panel.unavailable).toUpperCase()} is unreachable.` : 'This analytics query failed.'}
      {' '}{panel.error} No previous result is shown for this panel.
    </p>
  }
  return <div className="skeleton" style={{ height: h }} aria-label="Loading analytics panel" aria-busy="true" />
}

function Kpi({ label, value, sub }) {
  return (
    <div className="stat panel">
      <span className="label">{label}</span>
      <span className="stat__value">{value}</span>
      {sub && <span className="stat__sub muted">{sub}</span>}
    </div>
  )
}

function TrendChart({ points, grain }) {
  const [hover, setHover] = useState(null)
  const ref = useRef(null)
  const W = 760, H = 220, P = { l: 56, r: 12, t: 12, b: 26 }
  const max = Math.max(1, ...points.map((p) => p.sales_cents))
  const x = (i) => P.l + (points.length <= 1 ? 0 : (i / (points.length - 1)) * (W - P.l - P.r))
  const y = (v) => H - P.b - (v / max) * (H - P.t - P.b)
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.sales_cents).toFixed(1)}`).join('')
  const area = points.length ? `${line}L${x(points.length - 1)},${H - P.b}L${x(0)},${H - P.b}Z` : ''
  const ticks = [0, 0.5, 1].map((f) => f * max)
  const fmtBucket = (iso) => {
    const d = new Date(iso)
    return grain === 'hour'
      ? d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', timeZone: 'UTC' })
      : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })
  }
  const onMove = (e) => {
    if (!points.length) return
    const r = ref.current.getBoundingClientRect()
    const px = ((e.clientX - r.left) / r.width) * W
    const i = Math.round(((px - P.l) / (W - P.l - P.r)) * (points.length - 1))
    setHover(Math.max(0, Math.min(points.length - 1, i)))
  }
  if (!points.length) return <p className="muted">No orders in this range.</p>
  const hp = hover != null ? points[hover] : null
  return (
    <div className="ax-chart">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Sales over time" onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} className="ax-grid" />
            <text x={P.l - 8} y={y(t) + 4} className="ax-axis" textAnchor="end">{money(t)}</text>
          </g>
        ))}
        <text x={P.l} y={H - 6} className="ax-axis">{fmtBucket(points[0].bucket)}</text>
        <text x={W - P.r} y={H - 6} className="ax-axis" textAnchor="end">{fmtBucket(points[points.length - 1].bucket)}</text>
        <path d={area} className="ax-area" />
        <path d={line} className="ax-line" />
        {hp && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={H - P.b} className="ax-cross" />
            <circle cx={x(hover)} cy={y(hp.sales_cents)} r="4.5" className="ax-dot" />
          </g>
        )}
      </svg>
      {hp && (
        <div className="ax-tip panel" style={{ left: `${(x(hover) / W) * 100}%` }} role="status">
          <strong>{fmtBucket(hp.bucket)} UTC</strong>
          <span>Sales <b className="mono">{money(hp.sales_cents)}</b></span>
          <span>Orders <b className="mono">{num(hp.orders)}</b></span>
          <span>Cancelled/refunded <b className="mono">{num(hp.cancelled_or_refunded)}</b></span>
        </div>
      )}
    </div>
  )
}

function Bars({ rows, value, label }) {
  const max = Math.max(1, ...rows.map(value))
  return (
    <ul className="ax-bars">
      {rows.map((r) => (
        <li key={label(r)} title={`${label(r)}: ${money(value(r))}`}>
          <span className="ax-bars__label">{label(r)}</span>
          <span className="ax-bars__track"><span className="ax-bars__fill" style={{ width: `${(value(r) / max) * 100}%` }} /></span>
          <span className="mono ax-bars__value">{money(value(r))}</span>
        </li>
      ))}
    </ul>
  )
}

function Freshness({ tenant, mode }) {
  const [result, setResult] = useState({ tenant: null, data: null })
  useEffect(() => {
    let active = true
    let pending = false
    let controller = null
    const tick = async () => {
      if (pending) return
      pending = true
      controller = new AbortController()
      try {
        const data = await api.freshness(tenant, controller.signal)
        if (active) setResult({ tenant, data })
      } catch {
        if (active) setResult({ tenant, data: null })
      } finally {
        pending = false
      }
    }
    void tick()
    const id = setInterval(tick, 5000)
    return () => { active = false; clearInterval(id); controller?.abort() }
  }, [tenant])
  const raw = result.tenant === tenant ? result.data : null
  if (!raw || typeof raw !== 'object') return <p className="muted">Incremental engine status unavailable.</p>
  const verifiedAge = typeof raw.verified_age_s === 'number' && Number.isFinite(raw.verified_age_s) && raw.verified_age_s >= 0
    ? raw.verified_age_s : null
  const f = {
    ...raw,
    healthy: raw.healthy === true,
    verified_age_s: verifiedAge,
    stream_tables: Array.isArray(raw.stream_tables)
      ? raw.stream_tables.filter((table) => table && typeof table === 'object').map((table) => ({
        ...table,
        name: typeof table.name === 'string' ? table.name : 'unknown table',
        refresh_mode: typeof table.refresh_mode === 'string' ? table.refresh_mode : '—',
        schedule: typeof table.schedule === 'string' ? table.schedule : '—',
        last_action: typeof table.last_action === 'string' ? table.last_action : '—',
        age_s: typeof table.age_s === 'number' && Number.isFinite(table.age_s) && table.age_s >= 0 ? table.age_s : null,
      }))
      : [],
  }
  const explanation = mode === 'raw_source'
    ? 'Incremental engine health — not the freshness or correctness of current direct-source answers.'
    : mode === 'rollup'
      ? 'Last completed refresh age is not exact commit-to-visible delay or proof of stream-table correctness.'
      : 'Engine status does not verify the source mode, freshness, or correctness of every analytics panel.'
  return (
    <div>
      <p className="ax-fresh__head">
        <span className={`dot ${f.healthy && f.verified_age_s != null && f.verified_age_s < 30 ? 'dot--ok dot--pulse' : 'dot--warn'}`} />
        {f.verified_age_s != null
          ? <>Oldest completed stream refresh <b className="mono">{f.verified_age_s.toFixed(1)} s</b> ago</>
          : 'Incremental engine refresh age unavailable.'}
      </p>
      <p className="faint ax-note" role="note">{explanation}</p>
      <table className="ax-table">
        <thead><tr><th>Stream table</th><th>Mode</th><th>Last refresh</th><th>Verified</th></tr></thead>
        <tbody>
          {f.stream_tables.map((t) => (
            <tr key={t.name}>
              <td className="mono">{t.name}</td>
              <td>{t.refresh_mode} · {t.schedule}</td>
              <td>{t.last_action || '—'}</td>
              <td className="mono">{t.age_s != null ? `${t.age_s.toFixed(1)} s ago` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function LiveWrite({ tenant, onDone }) {
  const { notify } = useApp()
  const [busy, setBusy] = useState(false)
  const [last, setLast] = useState(null)
  const run = async (action) => {
    setBusy(true)
    try {
      const r = await api.liveWrite(tenant, action === 'cancel' ? { action, order_id: last?.order_id } : { action })
      setLast(r)
      onDone()
      notify({ kind: r.timed_out ? 'warn' : 'ok', title: `${action === 'cancel' ? 'Cancel' : 'Insert'} visibility sample`,
        message: r.lag_ms != null
          ? `Affected groups matched source in ${r.lag_ms} ms. One scoped sample; not proof of full stream-table correctness.`
          : 'Affected groups did not all match source within 30 s.' })
    } catch (err) {
      notify({ kind: 'error', title: 'Live write failed', message: err.message })
    } finally {
      setBusy(false)
    }
  }
  return (
    <div>
      <p className="muted">Demo-only write: commits a real order on this tenant's shard, then checks only the touched product/day/category/hour groups against source rows. A matching sample does not prove overall stream-table correctness or resolve the known G4 ghost-aggregate defect.</p>
      <div className="ax-row">
        <button className="btn btn--primary" disabled={busy} onClick={() => run('insert')}>
          {busy ? <span className="spinner" /> : <Icon name="plus" />} Insert order
        </button>
        <button className="btn" disabled={busy || !last || last.status === 'cancelled'} onClick={() => run('cancel')}>
          <Icon name="close" /> Cancel that order
        </button>
      </div>
      {last && (
        <div className="ax-live">
          <span className="label">Order {last.order_id} · {last.status}{last.shard ? ` · shard ${last.shard.toUpperCase()}` : ''}</span>
          <ul>
            {Object.entries(last.visible_after_ms).map(([k, v]) => <li key={k}><span className="mono">{k}</span> <b className="mono">{v} ms</b></li>)}
          </ul>
          {last.lag_ms != null && <p>Measured commit → touched groups matched source: <b className="mono">{last.lag_ms} ms</b> <span className="faint">(single sample; G4 remains open)</span></p>}
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { user } = useApp()
  const [tenants, setTenants] = useState([])
  const [tenant, setTenant] = useState(user.tenant_id || 1)
  const [preset, setPreset] = useState(PRESETS[2])
  const [grain, setGrain] = useState(preset.grain)
  const [by, setBy] = useState('category')
  const [auto, setAuto] = useState(true)
  const [minuteBucket, setMinuteBucket] = useState(() => Math.ceil(Date.now() / 60000))
  const [state, setState] = useState(() => ({ requestKey: null, loading: true, refreshing: false, panels: createLoadingPanels() }))
  const requestGate = useRef(null)
  if (requestGate.current === null) requestGate.current = createDashboardRequestGate()

  const [dirVersion, setDirVersion] = useState(null)
  useEffect(() => {
    api.tenants().then((r) => { setTenants(r.tenants); setDirVersion(r.directory_version) }).catch(() => setTenants([]))
  }, [])
  const shardOf = tenants.find((x) => x.tenant_id === tenant)?.shard

  const range = useMemo(() => {
    const to = new Date(minuteBucket * 60000) // minute-aligned so auto-refresh is cache-friendly
    return { from: new Date(to.getTime() - preset.ms).toISOString(), to: to.toISOString() }
  }, [preset, minuteBucket])
  const requestKey = dashboardQueryKey({ tenant, range, grain, by })

  const load = useCallback(async () => {
    const ticket = requestGate.current.begin(requestKey)
    if (!ticket) return
    setState((previous) => {
      const sameQuery = previous.requestKey === requestKey
      const panels = createLoadingPanels(sameQuery ? previous.panels : null)
      return {
        requestKey,
        loading: true,
        refreshing: sameQuery && Object.values(panels).some((panel) => panel.status === 'success'),
        panels,
      }
    })
    const signal = ticket.controller.signal
    const requests = [
      ['summary', () => api.summary(tenant, range, signal)],
      ['trends', () => api.trends(tenant, { ...range, grain }, signal)],
      ['products', () => api.topProducts(tenant, { ...range, limit: 10 }, signal)],
      ['breakdown', () => api.breakdown(tenant, { ...range, by }, signal)],
    ]
    const settled = await Promise.allSettled(requests.map(([, request]) => timed(request)))
    if (!requestGate.current.isCurrent(ticket)) return
    const settledByFamily = Object.fromEntries(requests.map(([family], index) => [family, settled[index]]))
    const panels = buildDashboardResults(settledByFamily, {
      requestedRange: range,
      requestedTenant: tenant,
      requestedGrain: grain,
      requestedBreakdown: by,
    })
    requestGate.current.finish(ticket)
    setState({ requestKey, loading: false, refreshing: false, panels, receivedAt: new Date().toISOString() })
  }, [by, grain, range, requestKey, tenant])

  useEffect(() => {
    const id = setTimeout(() => { void load() }, 0)
    return () => {
      clearTimeout(id)
      requestGate.current.cancel(requestKey)
    }
  }, [load, requestKey])

  useEffect(() => {
    if (!auto) return undefined
    const id = setInterval(() => {
      setMinuteBucket(Math.ceil(Date.now() / 60000))
      void load()
    }, 5000)
    return () => clearInterval(id)
  }, [auto, load])

  const choosePreset = (p) => {
    setPreset(p)
    setGrain(p.ms > 31 * 86400e3 ? 'day' : p.grain)
  }

  const current = state.requestKey === requestKey ? state : {
    requestKey, loading: true, refreshing: false, panels: createLoadingPanels(),
  }
  const { summary: s, trends: t, products: p, breakdown: b } = current.panels
  const sum = s?.status === 'success' ? s.data.summary : null
  const classification = classifyAnalyticsSet(current.panels)
  return (
    <div className="ax-dash">
      <div className="ax-filters panel">
        {user.role === 'admin' ? (
          <label className="ax-field">
            <span className="label">Tenant</span>
            <select className="select" value={tenant} onChange={(e) => setTenant(Number(e.target.value))}>
              {tenants.map((x) => <option key={x.tenant_id} value={x.tenant_id}>{x.tenant_id} · {x.name}{x.shard ? ` · shard ${x.shard.toUpperCase()}` : ''}</option>)}
            </select>
          </label>
        ) : (
          <div className="ax-field"><span className="label">Tenant</span><span className="mono">{tenant}</span></div>
        )}
        <div className="ax-field">
          <span className="label">Range</span>
          <div className="ax-seg" role="group" aria-label="Time range">
            {PRESETS.map((x) => (
              <button key={x.id} className={`btn btn--sm ${preset.id === x.id ? 'btn--primary' : 'btn--ghost'}`} onClick={() => choosePreset(x)}>{x.label}</button>
            ))}
          </div>
        </div>
        <div className="ax-field">
          <span className="label">Grain</span>
          <div className="ax-seg" role="group" aria-label="Trend grain">
            {['day', 'hour'].map((g) => (
              <button key={g} disabled={g === 'hour' && preset.ms > 31 * 86400e3}
                className={`btn btn--sm ${grain === g ? 'btn--primary' : 'btn--ghost'}`} onClick={() => setGrain(g)}>{g}</button>
            ))}
          </div>
        </div>
        <label className="ax-field ax-field--check">
          <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
          <span>Auto-refresh 5 s</span>
        </label>
        <span className="mono faint ax-range">{range.from.slice(0, 16)}Z → {range.to.slice(0, 16)}Z</span>
        <QueryFreshness classification={classification} summaryPanel={s} />
      </div>

      <DataSourceIndicator classification={classification} panels={current.panels} />
      {current.refreshing && <p className="faint ax-refreshing" role="status">Refreshing this tenant and range. Shown values are the last successful responses for these same filters until each panel finishes.</p>}
      {ANALYTICS_FAMILIES.some(([family]) => current.panels[family]?.status === 'error') && (
        <p className="alert ax-outage" role="alert">Some analytics panels are unavailable. Failed panels show no previous values; available panels retain their own response provenance.</p>
      )}
      {shardOf && <p className="mono faint ax-shardline">Tenant {tenant} lives on shard {shardOf.toUpperCase()} (directory v{dirVersion})</p>}

      <div className="ax-panel-provenance">
        <span className="faint">Summary panel source</span><PanelSourceBadge family="Summary" panel={s} />
      </div>
      <div className="stats ax-kpis">
        <Kpi label="Sales" value={sum ? money(sum.sales_cents) : '—'} sub="excl. cancelled & refunded" />
        <Kpi label="Orders" value={sum ? num(sum.sale_orders) : '—'} sub={sum ? `${num(sum.orders)} incl. all statuses` : ''} />
        <Kpi label="Avg order" value={sum ? money(sum.avg_order_cents) : '—'} sub={sum ? `${num(sum.units_sold)} units` : ''} />
        <Kpi label="Cancel / refund rate" value={sum ? pct(sum.cancel_rate) : '—'} sub={sum ? `${num(sum.cancelled_or_refunded)} orders` : ''} />
      </div>

      <section className="panel ax-panel">
        <div className="panel__head"><span className="panel__title">Sales by {grain}</span><PanelSourceBadge family="Trends" panel={t} /><Ms panel={t} /></div>
        <PanelContent panel={t} h={220}><TrendChart points={t?.data?.points} grain={grain} /></PanelContent>
      </section>

      <div className="ax-grid2">
        <section className="panel ax-panel">
          <div className="panel__head"><span className="panel__title">Top 10 products</span><PanelSourceBadge family="Top products" panel={p} /><Ms panel={p} /></div>
          <PanelContent panel={p} h={260}>
            <table className="ax-table">
              <thead><tr><th>#</th><th>Product</th><th className="num">Units</th><th className="num">Sales</th></tr></thead>
              <tbody>
                {(p?.data?.products || []).map((r) => (
                  <tr key={r.product_id}>
                    <td className="mono">{r.rank}</td>
                    <td>{r.name || `product ${r.product_id}`}<span className="faint"> · cat {r.category_id}</span></td>
                    <td className="num mono">{num(r.units_sold)}</td>
                    <td className="num mono">{money(r.sales_cents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PanelContent>
        </section>

        <section className="panel ax-panel">
          <div className="panel__head">
            <span className="panel__title">Breakdown</span>
            <PanelSourceBadge family="Breakdown" panel={b} />
            <div className="ax-seg">
              {['category', 'status'].map((k) => (
                <button key={k} className={`btn btn--sm ${by === k ? 'btn--primary' : 'btn--ghost'}`} onClick={() => setBy(k)}>{k}</button>
              ))}
            </div>
            <Ms panel={b} />
          </div>
          <PanelContent panel={b} h={260}>
            {b?.data?.by === 'category'
              ? <Bars rows={b?.data?.rows || []} value={(r) => r.sales_cents} label={(r) => 'Category ' + r.key} />
              : <Bars rows={b?.data?.rows || []} value={(r) => r.gross_cents} label={(r) => r.key} />}
          </PanelContent>
          {b?.status === 'success' && b.data.by === 'status' && <p className="faint ax-note">Status view shows gross order value per status, including cancelled and refunded.</p>}
        </section>
      </div>

      <section className="panel ax-panel">
        <div className="panel__head"><span className="panel__title">Config-driven metrics (B-4)</span></div>
        <ConfigMetrics tenant={tenant} range={range} refreshKey={state.receivedAt} />
      </section>

      <div className="ax-grid2">
        <section className="panel ax-panel">
          <div className="panel__head">
            <span className="panel__title">{classification.mode === 'raw_source'
              ? 'Incremental engine health — not direct-source answer freshness'
              : 'Incremental engine status'}</span>
          </div>
          <Freshness tenant={tenant} mode={classification.mode} />
        </section>
        <section className="panel ax-panel">
          <div className="panel__head"><span className="panel__title">Live mutation sample</span></div>
          <LiveWrite tenant={tenant} onDone={() => { void load() }} />
        </section>
      </div>

    </div>
  )
}
