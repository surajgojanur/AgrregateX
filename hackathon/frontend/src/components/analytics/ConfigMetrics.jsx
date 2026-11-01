import { useEffect, useState } from 'react'
import { api } from '../../api/client'

// B-4: renders whatever metrics hackathon/app/config/metrics.json defines. Adding a metric there makes it
// appear here on the next refresh, with no change to this file. Formatting follows the metric's declared unit.
const fmt = (m, v) => {
  if (v == null) return '—'
  if (m.unit === 'cents') {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(v / 100)
  }
  const n = new Intl.NumberFormat(undefined, { maximumFractionDigits: m.decimals }).format(v)
  return m.unit === 'percent' ? `${n}%` : n
}

const describe = (part) => `${part.measure} [${part.statuses}]`

export default function ConfigMetrics({ tenant, range, refreshKey }) {
  const [state, setState] = useState({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    ;(async () => {
      try {
        const reg = await api.metrics(signal)
        const values = await Promise.allSettled(
          reg.metrics.map((m) => api.metric(tenant, m.id, { ...range, group_by: 'total' }, signal)))
        if (signal.aborted) return
        setState({ status: 'success', reg, values })
      } catch (err) {
        if (err?.name === 'AbortError' || signal.aborted) return
        setState({ status: 'error', message: err.message, errors: err.data?.detail?.errors || [] })
      }
    })()
    return () => controller.abort()
  }, [tenant, range, refreshKey])

  if (state.status === 'loading') return <div className="skeleton" style={{ height: 120 }} aria-busy="true" aria-label="Loading config-driven metrics" />
  if (state.status === 'error') {
    return (
      <div className="alert ax-panel-error" role="alert">
        Config-driven metrics are unavailable. {state.errors.length ? 'The metric config was rejected:' : state.message}
        {state.errors.length > 0 && <ul className="mono">{state.errors.map((e) => <li key={e}>{e}</li>)}</ul>}
      </div>
    )
  }
  const { reg, values } = state
  return (
    <>
      <table className="ax-table">
        <thead><tr><th>Metric</th><th className="num">Value</th><th>Definition (from config)</th></tr></thead>
        <tbody>
          {reg.metrics.map((m, i) => {
            const r = values[i]
            const total = r.status === 'fulfilled' ? r.value.total : null
            return (
              <tr key={m.id}>
                <td>{m.label}<div className="mono faint">{m.id}</div></td>
                <td className="num mono">
                  {r.status === 'rejected' ? <span className="faint">{r.reason?.message || 'failed'}</span> : fmt(m, total?.value)}
                  {total?.undefined_reason && <div className="faint">no {m.denominator?.measure} in range</div>}
                </td>
                <td className="mono faint">
                  {m.type === 'ratio' ? `${describe(m.numerator)} ÷ ${describe(m.denominator)}${m.scale !== 1 ? ` × ${m.scale}` : ''}` : `sum ${describe(m.numerator)}`}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="faint ax-note">
        Registry v{reg.registry_version} · {reg.metrics.length} metrics · derived from the existing stream tables
        ({[...new Set(reg.metrics.flatMap((m) => m.derived_from))].join(', ')}). No SQL in config.
      </p>
    </>
  )
}
