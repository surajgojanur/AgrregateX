import { useEffect, useState } from 'react'
import { api } from '../api/client'

const num = (n) => (n == null ? '—' : new Intl.NumberFormat().format(n))

function ShardCard({ s }) {
  const ok = s.available && s.healthy !== false
  return (
    <section className={`panel ax-panel ${s.available ? '' : 'ax-outage'}`}>
      <div className="ax-shard__head">
        <span className={`dot ${s.available ? (ok ? 'dot--ok dot--pulse' : 'dot--warn') : 'dot--err'}`} />
        <h3>Shard {s.shard.toUpperCase()}</h3>
        <span className="label" style={{ marginLeft: 'auto' }}>{s.available ? `probe ${s.probe_ms} ms` : `UNAVAILABLE · ${s.error || ''}`}</span>
      </div>
      <dl className="ax-kv">
        <dt>Host</dt><dd className="mono">{s.host}</dd>
        <dt>Tenants (directory)</dt><dd className="mono">{(s.tenants || []).join(', ') || '—'}</dd>
        <dt>Orders</dt><dd className="mono">{s.available ? `${num(s.orders)} (seed ${num(s.seed_orders)})` : 'unknown while unreachable'}</dd>
        <dt>Pending CDC rows</dt><dd className="mono">{s.available ? num(s.pending_cdc_rows) : '—'}</dd>
        <dt>Directory violations</dt><dd className={`mono ${s.directory_violations?.length ? 'text-red' : ''}`}>{s.available ? (s.directory_violations?.length ? s.directory_violations.join(', ') : 'none') : '—'}</dd>
      </dl>
      {s.available && (
        <table className="ax-table">
          <thead><tr><th>Stream table</th><th>Status</th><th>Mode</th><th>Verified</th></tr></thead>
          <tbody>
            {s.stream_tables.map((t) => (
              <tr key={t.name}><td className="mono">{t.name}</td><td>{t.status}</td><td>{t.refresh_mode}</td>
                <td className="mono">{t.age_s != null ? `${t.age_s.toFixed(1)} s ago` : '—'}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

export default function Shards() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    let live = true
    const tick = () => api.shards().then((x) => { if (live) { setD(x); setErr(null) } }).catch((x) => live && setErr(x.message))
    tick()
    const id = setInterval(tick, 3000)
    return () => { live = false; clearInterval(id) }
  }, [])
  if (err) return <p className="alert" role="alert">{`Shard overview unavailable: ${err}. This database may require the current sharding schema; no availability data is assumed.`}</p>
  if (!d) return <div className="skeleton" style={{ height: 300 }} />
  return (
    <div className="ax-dash">
      <div className="stats ax-kpis">
        <div className="stat panel"><span className="label">Directory</span><span className="stat__value">v{d.directory_version ?? '—'}</span><span className="stat__sub muted">stable tenant → shard map</span></div>
        <div className="stat panel"><span className="label">Shards up</span><span className="stat__value">{d.shards.length - d.missing_shards.length} / {d.shards.length}</span><span className="stat__sub muted">{d.complete ? 'all reachable' : `missing: ${d.missing_shards.join(', ').toUpperCase()}`}</span></div>
        <div className="stat panel"><span className="label">{d.complete ? 'Total orders (all shards)' : 'PARTIAL total'}</span>
          <span className={`stat__value ${d.complete ? '' : 'text-amber'}`}>{num(d.complete ? d.total_orders : d.partial_total_orders)}</span>
          <span className="stat__sub muted">{d.complete ? 'complete' : 'incomplete: excludes unreachable shards'}</span></div>
      </div>
      {!d.complete && <p className="alert ax-outage" role="alert">Global view is PARTIAL. Shard(s) {d.missing_shards.join(', ').toUpperCase()} unreachable; their tenants return 503 and are excluded from totals.</p>}
      <div className="ax-shards">{d.shards.map((s) => <ShardCard key={s.shard} s={s} />)}</div>
      <p className="faint ax-note">Fail-closed per shard: no cross-shard fallback, no replication or automatic failover in this demo.</p>
    </div>
  )
}
