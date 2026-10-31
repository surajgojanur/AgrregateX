import { useEffect, useState } from 'react'

export default function Monitoring() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    let stopped = false
    let timer
    const controller = new AbortController()
    async function tick() {
      try {
        const response = await fetch('/api/monitoring', { signal: controller.signal, credentials: 'same-origin' })
        if (!response.ok) throw new Error(`Monitoring unavailable (HTTP ${response.status}). Operator sign-in required.`)
        const value = await response.json()
        if (!stopped) { setData(value); setError(null) }
      } catch (e) { if (!stopped) { setError(e.message); setData(null) } }
      if (!stopped) timer = setTimeout(tick, 15000)
    }
    tick()
    return () => { stopped = true; clearTimeout(timer); controller.abort() }
  }, [])
  if (error) return <div className="panel ax-panel" role="alert">{error}</div>
  if (!data) return <p role="status">Loading monitoring…</p>
  const a = data.api
  return <div className="ax-dash">
    <section className="panel ax-panel"><h2>API request performance</h2>
      <p>Successful latency p50: {a.p50_ms ?? '—'} ms · p95: {a.p95_ms ?? '—'} ms</p>
      <p>Success: {a.success} · HTTP errors: {a.errors} · Server timeouts: {a.timeouts}</p>
      <p>{data.scope}</p><p>Observed: {data.observed_at} · Collection interval: {data.cache_ttl_s}s</p>
    </section>
    {data.shards.map(s => <section className="panel ax-panel" key={s.shard}>
      <h2>Shard {s.shard.toUpperCase()} — {s.state}</h2>
      {s.engine ? <>
        <p>pg_trickle {s.engine.pg_trickle_version} · Scheduler: {s.engine.scheduler_running ? 'running' : 'stopped'}</p>
        <h3>Last successful refresh per stream table</h3>
        {s.freshness.map(t => <p key={t.name}>{t.name}: {t.verified_at ?? 'never observed'} · Age at collection: {t.age_s?.toFixed(1) ?? 'unknown'}s · {t.status} · Errors: {t.consecutive_errors}</p>)}
        <h3>Actual refresh history — last five minutes</h3>
        {s.engine.refresh_stats_5m.map(r => <p key={r.name}>{r.name}: {r.refreshes} refreshes · {r.failed} failed · {r.differential} differential · {r.full} full · {r.fallbacks} fallbacks · p95 {r.p95_ms ?? '—'} ms</p>)}
        <h3>Estimated CDC backlog (PostgreSQL statistics)</h3>
        {s.engine.change_buffers.map(b => <p key={b.buffer}>{b.buffer}: approximately {b.pending_rows} rows · {b.bytes} bytes</p>)}
        <h3>Database health</h3>{s.engine.health.map(h => <p key={h.check_name}>{h.check_name}: {h.severity}</p>)}
      </> : <p role="alert">{s.detail}</p>}
    </section>)}
    <p>Refresh age measures the last successful verification, including NO_DATA; it is not commit-to-visible latency. This page does not establish the official performance targets.</p>
  </div>
}
