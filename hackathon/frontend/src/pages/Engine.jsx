import { useEffect, useState } from 'react'
import { api } from '../api/client'

const kb = (b) => (b == null ? '—' : b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.round(b / 1024)} kB`)
const sev = { OK: 'dot--ok', WARN: 'dot--warn', ERROR: 'dot--err', UNKNOWN: 'dot--idle' }

export default function Engine() {
  const [e, setE] = useState(null)
  const [err, setErr] = useState(null)
  const [shard, setShard] = useState(null)
  const [limits, setLimits] = useState(null)
  useEffect(() => {
    let live = true
    const tick = () => api.limits().then((d) => live && setLimits(d)).catch(() => live && setLimits(null))
    tick()
    const id = setInterval(tick, 3000)
    return () => { live = false; clearInterval(id) }
  }, [])
  useEffect(() => {
    let live = true
    const tick = () => api.engine(shard).then((d) => { if (live) { setE(d); setErr(null) } }).catch((x) => live && setErr(x.message))
    tick()
    const id = setInterval(tick, 3000)
    return () => { live = false; clearInterval(id) }
  }, [shard])

  const picker = e?.shards?.length > 1 && (
    <div className="ax-filters panel">
      <div className="ax-field"><span className="label">Shard</span>
        <div className="ax-seg">{e.shards.map((s) => (
          <button key={s} className={`btn btn--sm ${(shard || e.shard) === s ? 'btn--primary' : 'btn--ghost'}`} onClick={() => { setE(null); setShard(s) }}>{s.toUpperCase()}</button>
        ))}</div>
      </div>
    </div>
  )
  if (err) return <div className="ax-dash">{picker}<p className="alert" role="alert">{err}</p>{!e && <button className="btn" onClick={() => setShard(shard === 'a' ? 'b' : 'a')}>Try the other shard</button>}</div>
  if (!e) return <div className="skeleton" style={{ height: 300 }} />
  const problems = e.health.filter((h) => h.severity !== 'OK')
  return (
    <div className="ax-dash">
      {picker}
      <div className="stats ax-kpis">
        <div className="stat panel"><span className="label">pg_trickle</span><span className="stat__value">{e.pg_trickle_version}</span><span className="stat__sub muted">upstream engine (trickle-labs)</span></div>
        <div className="stat panel"><span className="label">Scheduler</span><span className="stat__value">{e.scheduler_running ? 'running' : 'stopped'}</span><span className="stat__sub muted">background worker for this DB</span></div>
        <div className="stat panel"><span className="label">CDC mode</span><span className="stat__value">{e.stream_tables[0]?.cdc_mode || '—'}</span><span className="stat__sub muted">wal_level={e.settings.wal_level}</span></div>
        <div className="stat panel"><span className="label">Health</span><span className="stat__value">{problems.length ? `${problems.length} issue(s)` : 'OK'}</span><span className="stat__sub muted">pgtrickle.health_check()</span></div>
      </div>

      <section className="panel ax-panel">
        <div className="panel__head"><span className="panel__title">Stream tables</span><span className="label">configured vs effective mode</span></div>
        <table className="ax-table">
          <thead><tr><th>Name</th><th>Status</th><th>Configured</th><th>Effective (last)</th><th>Schedule</th><th className="num">Rows</th><th className="num">Size</th><th className="num">Errors</th></tr></thead>
          <tbody>
            {e.stream_tables.map((t) => (
              <tr key={t.name}>
                <td className="mono">{t.name}</td><td>{t.status}</td><td>{t.refresh_mode}</td><td>{t.effective_refresh_mode}</td>
                <td>{t.schedule}</td><td className="num mono">{t.approx_rows}</td><td className="num mono">{kb(t.bytes)}</td><td className="num mono">{t.consecutive_errors}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className="ax-grid2">
        <section className="panel ax-panel">
          <div className="panel__head"><span className="panel__title">Refreshes · last 5 min</span></div>
          <table className="ax-table">
            <thead><tr><th>Name</th><th className="num">Total</th><th className="num">Diff</th><th className="num">Full</th><th className="num">Fallback</th><th className="num">Failed</th><th className="num">p50</th><th className="num">p95</th><th className="num">Max</th></tr></thead>
            <tbody>
              {e.refresh_stats_5m.map((r) => (
                <tr key={r.name}>
                  <td className="mono">{r.name}</td><td className="num mono">{r.refreshes}</td><td className="num mono">{r.differential}</td>
                  <td className="num mono">{r.full}</td><td className={`num mono ${r.fallbacks ? 'text-amber' : ''}`}>{r.fallbacks}</td>
                  <td className={`num mono ${r.failed ? 'text-red' : ''}`}>{r.failed}</td>
                  <td className="num mono">{r.p50_ms ?? '—'}</td><td className="num mono">{r.p95_ms ?? '—'}</td><td className="num mono">{r.max_ms ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="faint ax-note">Durations in ms, excluding no-change ticks. A FULL or fallback on a DIFFERENTIAL table means the incremental path was not used.</p>
        </section>
        <section className="panel ax-panel">
          <div className="panel__head"><span className="panel__title">Change buffers (CDC backlog)</span></div>
          <table className="ax-table">
            <thead><tr><th>Buffer</th><th className="num">Pending rows</th><th className="num">Size</th></tr></thead>
            <tbody>{e.change_buffers.map((c) => <tr key={c.buffer}><td className="mono">{c.buffer}</td><td className="num mono">{c.pending_rows}</td><td className="num mono">{kb(c.bytes)}</td></tr>)}</tbody>
          </table>
          <span className="label ax-sub">Health checks</span>
          <ul className="ax-health">
            {e.health.map((h) => <li key={h.check_name}><span className={`dot ${sev[h.severity] || 'dot--idle'}`} /> <span className="mono">{h.check_name}</span> <span className="faint">{h.severity !== 'OK' ? h.detail : ''}</span></li>)}
          </ul>
        </section>
      </div>

      <section className="panel ax-panel">
        <div className="panel__head"><span className="panel__title">Recent refreshes</span><span className="label">pgtrickle.pgt_refresh_history</span></div>
        <table className="ax-table">
          <thead><tr><th>Started</th><th>Stream table</th><th>Action</th><th>Status</th><th className="num">ms</th><th className="num">Delta rows</th><th className="num">Rows changed</th><th>Reason</th></tr></thead>
          <tbody>
            {e.recent_refreshes.map((r, i) => (
              <tr key={`${r.start_time}-${i}`}>
                <td className="mono">{new Date(r.start_time).toLocaleTimeString()}</td><td className="mono">{r.name}</td>
                <td className={r.action === 'FULL' ? 'text-amber' : ''}>{r.action}</td><td className={r.status === 'FAILED' ? 'text-red' : ''}>{r.status}</td>
                <td className="num mono">{r.ms}</td><td className="num mono">{r.delta_rows}</td><td className="num mono">{r.rows_changed}</td><td className="faint">{r.reason || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {limits && (
        <section className="panel ax-panel">
          <div className="panel__head"><span className="panel__title">Per-tenant query limits (B-3)</span>
            <span className="label">max {limits.max_concurrent_per_tenant} concurrent / tenant · wait {limits.queue_wait_s} s · {limits.scope}</span></div>
          {limits.tenants.length === 0 ? <p className="muted">No analytics queries yet.</p> : (
            <table className="ax-table">
              <thead><tr><th>Tenant</th><th className="num">In flight</th><th className="num">Peak</th><th className="num">Admitted</th><th className="num">Rejected (429)</th></tr></thead>
              <tbody>{limits.tenants.map((t) => (
                <tr key={t.tenant_id}><td className="mono">{t.tenant_id}</td><td className="num mono">{t.in_flight}</td><td className="num mono">{t.peak}</td>
                  <td className="num mono">{t.admitted}</td><td className={`num mono ${t.rejected_429 ? 'text-amber' : ''}`}>{t.rejected_429}</td></tr>
              ))}</tbody>
            </table>
          )}
        </section>
      )}

      <section className="panel ax-panel">
        <div className="panel__head"><span className="panel__title">Settings (live SHOW)</span></div>
        <table className="ax-table"><tbody>{Object.entries(e.settings).map(([k, v]) => <tr key={k}><td className="mono">{k}</td><td className="mono">{v}</td></tr>)}</tbody></table>
      </section>
    </div>
  )
}
