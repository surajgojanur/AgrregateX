import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import Icon from '../components/ui/Icon'
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
  return { data, ms: Math.round(performance.now() - t0) }
}

function Ms({ ms }) {
  return ms == null ? null : <span className="mono faint ax-ms" title="Measured HTTP round trip from this browser">{ms} ms</span>
}

function Pending({ h, down }) {
  return down
    ? <p className="muted" style={{ minHeight: h / 3 }}>Unavailable: shard {String(down).toUpperCase()} is unreachable. No data shown rather than stale data.</p>
    : <div className="skeleton" style={{ height: h }} />
}

// B-1: "Updated N s ago" from the response's freshness block (oldest stream table's last
// completed refresh). Ticks every second; amber beyond 30 s (the PRD's great-freshness line).
function FreshBadge({ fresh }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  if (!fresh) return null
  if (!fresh.verified_at) return <span className="ax-fresh ax-fresh--warn" role="status">Freshness unknown</span>
  const age = Math.max(0, Math.round((now - Date.parse(fresh.verified_at)) / 1000))
  const text = age < 60 ? `${age} s` : `${Math.floor(age / 60)} min ${age % 60} s`
  return (
    <span className={`ax-fresh ${age > 30 || !fresh.healthy ? 'ax-fresh--warn' : ''}`} role="status"
      title={`Every number shown is at least as fresh as ${new Date(fresh.verified_at).toLocaleTimeString()} (${fresh.rule})`}>
      <span className={`dot ${age > 30 || !fresh.healthy ? 'dot--warn' : 'dot--ok dot--pulse'}`} /> Updated {text} ago
    </span>
  )
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

function Freshness({ tenant }) {
  const [f, setF] = useState(null)
  useEffect(() => {
    let live = true
    const tick = () => api.freshness(tenant).then((d) => live && setF(d)).catch(() => live && setF(null))
    tick()
    const id = setInterval(tick, 2000)
    return () => { live = false; clearInterval(id) }
  }, [tenant])
  if (!f) return <p className="muted">Freshness unavailable.</p>
  return (
    <div>
      <p className="ax-fresh__head">
        <span className={`dot ${f.healthy && f.verified_age_s != null && f.verified_age_s < 30 ? 'dot--ok dot--pulse' : 'dot--warn'}`} />
        {f.verified_age_s != null
          ? <>All stream tables verified within <b className="mono">{f.verified_age_s.toFixed(1)} s</b></>
          : 'Waiting for first refresh…'}
      </p>
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
      <p className="faint ax-note">“Verified” = last completed refresh of any kind (including no-change ticks), not pg_trickle's data_timestamp, which does not move while idle.</p>
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
      notify({ kind: r.timed_out ? 'warn' : 'ok', title: `${action === 'cancel' ? 'Cancel' : 'Insert'} visible`,
        message: r.lag_ms != null ? `Commit → visible in all stream tables: ${r.lag_ms} ms` : 'Not visible within 30 s' })
    } catch (err) {
      notify({ kind: 'error', title: 'Live write failed', message: err.message })
    } finally {
      setBusy(false)
    }
  }
  return (
    <div>
      <p className="muted">Commits a real order on this tenant's shard, then polls until each stream table's affected row equals the same aggregate computed from raw orders.</p>
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
          {last.lag_ms != null && <p>Measured commit → visible (all tables): <b className="mono">{last.lag_ms} ms</b></p>}
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { user, notify } = useApp()
  const [tenants, setTenants] = useState([])
  const [tenant, setTenant] = useState(user.tenant_id || 1)
  const [preset, setPreset] = useState(PRESETS[2])
  const [grain, setGrain] = useState(preset.grain)
  const [by, setBy] = useState('category')
  const [auto, setAuto] = useState(true)
  const [state, setState] = useState({ loading: true })
  const [tick, setTick] = useState(0)

  const [dirVersion, setDirVersion] = useState(null)
  useEffect(() => {
    api.tenants().then((r) => { setTenants(r.tenants); setDirVersion(r.directory_version) }).catch(() => setTenants([]))
  }, [])
  const shardOf = tenants.find((x) => x.tenant_id === tenant)?.shard

  const range = useMemo(() => {
    const to = new Date(Math.ceil(Date.now() / 60000) * 60000) // minute-aligned so auto-refresh is cache-friendly
    return { from: new Date(to.getTime() - preset.ms).toISOString(), to: to.toISOString() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset, tick])

  const load = useCallback(async (signal) => {
    try {
      const [s, t, p, b] = await Promise.all([
        timed(() => api.summary(tenant, range, signal)),
        timed(() => api.trends(tenant, { ...range, grain }, signal)),
        timed(() => api.topProducts(tenant, { ...range, limit: 10 }, signal)),
        timed(() => api.breakdown(tenant, { ...range, by }, signal)),
      ])
      setState({ loading: false, s, t, p, b, at: new Date() })
    } catch (err) {
      if (err.name === 'AbortError') return
      // Shard outage: drop previous numbers so nothing stale is shown as current.
      if (err.status === 503) setState({ loading: false, error: err.message, unavailable: err.data?.shard || '?' })
      else setState((st) => ({ ...st, loading: false, error: err.message }))
      notify({ kind: 'error', title: 'Could not load dashboard', message: err.message })
    }
  }, [tenant, range, grain, by, notify])

  useEffect(() => {
    const ctl = new AbortController()
    void load(ctl.signal)
    return () => ctl.abort()
  }, [load])

  useEffect(() => {
    if (!auto) return undefined
    const id = setInterval(() => setTick((n) => n + 1), 5000)
    return () => clearInterval(id)
  }, [auto])

  const choosePreset = (p) => {
    setPreset(p)
    setGrain(p.ms > 31 * 86400e3 ? 'day' : p.grain)
  }

  const { s, t, p, b } = state
  const sum = s?.data.summary
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
        <FreshBadge fresh={state.s?.data.freshness} />
      </div>

      {shardOf && <p className="mono faint ax-shardline">Tenant {tenant} lives on shard {shardOf.toUpperCase()} (directory v{dirVersion})</p>}
      {state.unavailable ? (
        <div className="alert ax-outage" role="alert">
          <strong>Shard {String(state.unavailable).toUpperCase()} unavailable.</strong> {state.error}
          <span className="faint"> Retrying every 5 s. Tenants on other shards are unaffected.</span>
        </div>
      ) : state.error && <p className="alert" role="alert">{state.error}</p>}

      <div className="stats ax-kpis">
        <Kpi label="Sales" value={sum ? money(sum.sales_cents) : '—'} sub="excl. cancelled & refunded" />
        <Kpi label="Orders" value={sum ? num(sum.sale_orders) : '—'} sub={sum ? `${num(sum.orders)} incl. all statuses` : ''} />
        <Kpi label="Avg order" value={sum ? money(sum.avg_order_cents) : '—'} sub={sum ? `${num(sum.units_sold)} units` : ''} />
        <Kpi label="Cancel / refund rate" value={sum ? pct(sum.cancel_rate) : '—'} sub={sum ? `${num(sum.cancelled_or_refunded)} orders` : ''} />
      </div>

      <section className="panel ax-panel">
        <div className="panel__head"><span className="panel__title">Sales by {grain}</span><Ms ms={t?.ms} /></div>
        {t ? <TrendChart points={t.data.points} grain={grain} /> : <Pending h={220} down={state.unavailable} />}
      </section>

      <div className="ax-grid2">
        <section className="panel ax-panel">
          <div className="panel__head"><span className="panel__title">Top 10 products</span><Ms ms={p?.ms} /></div>
          {p ? (
            <table className="ax-table">
              <thead><tr><th>#</th><th>Product</th><th className="num">Units</th><th className="num">Sales</th></tr></thead>
              <tbody>
                {p.data.products.map((r) => (
                  <tr key={r.product_id}>
                    <td className="mono">{r.rank}</td>
                    <td>{r.name || `product ${r.product_id}`}<span className="faint"> · cat {r.category_id}</span></td>
                    <td className="num mono">{num(r.units_sold)}</td>
                    <td className="num mono">{money(r.sales_cents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Pending h={260} down={state.unavailable} />}
        </section>

        <section className="panel ax-panel">
          <div className="panel__head">
            <span className="panel__title">Breakdown</span>
            <div className="ax-seg">
              {['category', 'status'].map((k) => (
                <button key={k} className={`btn btn--sm ${by === k ? 'btn--primary' : 'btn--ghost'}`} onClick={() => setBy(k)}>{k}</button>
              ))}
            </div>
            <Ms ms={b?.ms} />
          </div>
          {b ? (
            b.data.by === 'category'
              ? <Bars rows={b.data.rows} value={(r) => r.sales_cents} label={(r) => `Category ${r.key}`} />
              : <Bars rows={b.data.rows} value={(r) => r.gross_cents} label={(r) => r.key} />
          ) : <Pending h={260} down={state.unavailable} />}
          {b?.data.by === 'status' && <p className="faint ax-note">Status view shows gross order value per status, including cancelled and refunded.</p>}
        </section>
      </div>

      <div className="ax-grid2">
        <section className="panel ax-panel">
          <div className="panel__head"><span className="panel__title">Freshness</span></div>
          <Freshness tenant={tenant} />
        </section>
        <section className="panel ax-panel">
          <div className="panel__head"><span className="panel__title">Live mutation</span></div>
          <LiveWrite tenant={tenant} onDone={() => setTick((n) => n + 1)} />
        </section>
      </div>

      {s && (
        <p className="faint ax-note">
          Source of these numbers: stream tables for complete UTC days{s.data.source.stream_table_range ? ` (${s.data.source.stream_table_range[0].slice(0, 10)} → ${s.data.source.stream_table_range[1].slice(0, 10)})` : ''},
          raw orders for {s.data.source.raw_edge_ranges.length} partial edge range(s). Updated {state.at?.toLocaleTimeString()}.
        </p>
      )}
    </div>
  )
}
