import { useEffect, useMemo, useState } from 'react'
import { api, assetUrl } from '../api/client'
import CompareSlider from '../components/sketch/CompareSlider'
import EmptyState from '../components/ui/EmptyState'
import Icon from '../components/ui/Icon'
import { formatDateTime, markLabel, optionLabel } from '../lib/format'
import { navigate } from '../lib/router'
import { useApp } from '../state/AppContext'

function Picker({ label, sketches, value, onChange, cache }) {
  const revs = cache[value.sketch]?.revisions || []
  return (
    <div className="picker">
      <span className="label">{label}</span>
      <select className="select select--sm" value={value.sketch || ''} onChange={(e) => onChange({ sketch: e.target.value, rev: null })} aria-label={`${label} sketch`}>
        {sketches.map((s) => <option key={s.id} value={s.id}>{s.id} · {s.title}</option>)}
      </select>
      <select className="select select--sm" value={value.rev || ''} onChange={(e) => onChange({ ...value, rev: Number(e.target.value) })} aria-label={`${label} revision`} disabled={!revs.length}>
        {revs.map((r) => <option key={r.number} value={r.number}>R{r.number} · {r.is_ai ? 'AI' : 'Procedural'} · {formatDateTime(r.created_at)}</option>)}
      </select>
    </div>
  )
}

export default function Compare({ params }) {
  const { catalog } = useApp()
  const [sketches, setSketches] = useState(null)
  const [cache, setCache] = useState({})
  const [a, setA] = useState({ sketch: params.sketch || null, rev: null })
  const [b, setB] = useState({ sketch: params.sketch || null, rev: null })
  const [view, setView] = useState('slider')
  const [error, setError] = useState(null)

  useEffect(() => {
    api.listSketches().then((r) => {
      setSketches(r.sketches)
      const first = params.sketch || r.sketches[0]?.id || null
      setA((x) => ({ ...x, sketch: x.sketch || first }))
      setB((x) => ({ ...x, sketch: x.sketch || first }))
    }).catch((e) => setError(e.message))
  }, [params.sketch])

  useEffect(() => {
    for (const id of [a.sketch, b.sketch]) {
      if (id && !cache[id]) {
        api.getSketch(id)
          .then((s) => setCache((c) => ({ ...c, [id]: s })))
          .catch((e) => setError(e.message))
      }
    }
  }, [a.sketch, b.sketch, cache])

  // Default: previous vs current revision of the same sketch.
  const revA = useMemo(() => {
    const s = cache[a.sketch]
    if (!s) return null
    const n = a.rev ?? (a.sketch === b.sketch ? Math.max(1, s.current.number - 1) : s.current.number)
    return s.revisions.find((r) => r.number === n) || s.current
  }, [cache, a, b.sketch])
  const revB = useMemo(() => {
    const s = cache[b.sketch]
    if (!s) return null
    return s.revisions.find((r) => r.number === (b.rev ?? s.current.number)) || s.current
  }, [cache, b])

  const diff = useMemo(() => {
    if (!revA || !revB) return []
    return catalog.traits.map((t) => {
      const va = revA.profile.traits?.[t.key]?.value ?? null
      const vb = revB.profile.traits?.[t.key]?.value ?? null
      return { key: t.key, label: t.label, a: optionLabel(t, va), b: optionLabel(t, vb), changed: va !== vb, known: va || vb }
    })
  }, [revA, revB, catalog])
  const adjDiff = useMemo(() => {
    if (!revA || !revB) return []
    return catalog.adjustments
      .map((x) => ({ label: x.label, a: revA.profile.adjustments?.[x.key] ?? 0, b: revB.profile.adjustments?.[x.key] ?? 0 }))
      .filter((x) => x.a !== x.b)
  }, [revA, revB, catalog])
  const [onlyChanged, setOnlyChanged] = useState(true)

  if (sketches && sketches.length === 0) {
    return (
      <EmptyState icon="compare" title="Nothing to compare yet"
        action={<button type="button" className="btn btn--primary" onClick={() => navigate('new', { fresh: Date.now().toString(36) })}><Icon name="plus" /> Create a sketch</button>}>
        Save a composite and at least one revision to compare versions side by side.
      </EmptyState>
    )
  }

  const changedCount = diff.filter((d) => d.changed).length
  const sid = (r, x) => `${x.sketch} · R${r.number}`

  return (
    <div className="compare-page reveal">
      {error && <div className="alert alert--error"><Icon name="error" /><span>{error}</span></div>}
      <div className="toolbar panel">
        {sketches ? (
          <>
            <Picker label="Version A" sketches={sketches} value={{ ...a, rev: revA?.number }} onChange={setA} cache={cache} />
            <Icon name="arrowRight" className="icon faint" />
            <Picker label="Version B" sketches={sketches} value={{ ...b, rev: revB?.number }} onChange={setB} cache={cache} />
          </>
        ) : <div className="skeleton" style={{ height: 34, flex: 1 }} />}
        <div className="segmented" role="group" aria-label="Comparison view">
          <button type="button" aria-pressed={view === 'slider'} onClick={() => setView('slider')}>Drag reveal</button>
          <button type="button" aria-pressed={view === 'split'} onClick={() => setView('split')}>Side by side</button>
        </div>
      </div>

      {revA && revB ? (
        <div className="compare-page__grid">
          <section className="panel panel--corners compare-page__stage">
            {view === 'slider' ? (
              <CompareSlider before={assetUrl(revA.image_url)} after={assetUrl(revB.image_url)} beforeLabel={`A · ${sid(revA, a)}`} afterLabel={`B · ${sid(revB, b)}`} />
            ) : (
              <div className="split">
                {[[revA, a, 'A'], [revB, b, 'B']].map(([r, x, k]) => (
                  <figure key={k}>
                    <img src={assetUrl(r.image_url)} alt={`Version ${k}`} />
                    <figcaption className="mono">{k} · {sid(r, x)}</figcaption>
                  </figure>
                ))}
              </div>
            )}
            <dl className="compare-meta">
              {[[revA, a, 'A'], [revB, b, 'B']].map(([r, x, k]) => (
                <div key={k} className="compare-meta__col">
                  <dt className="label">Version {k}</dt>
                  <dd className="mono">{sid(r, x)}</dd>
                  <dd><span className={`tag ${r.is_ai ? 'tag--ai' : 'tag--procedural'}`}>{r.is_ai ? 'AI-generated' : 'Procedural'}</span> <span className="faint">{r.method_label}</span></dd>
                  <dd className="mono faint">{formatDateTime(r.created_at)}</dd>
                  {r.change_note && <dd className="muted">“{r.change_note}”</dd>}
                </div>
              ))}
            </dl>
            <p className="faint compare-page__note"><Icon name="info" /> Visual comparison only. Revelio does not compute similarity scores or identity probabilities.</p>
          </section>

          <section className="panel" aria-labelledby="diff-title">
            <div className="panel__head">
              <h2 id="diff-title" className="panel__title section-title">Trait profiles</h2>
              <span className="chip chip--cyan mono">{changedCount} changed</span>
            </div>
            <div className="panel__body">
              <label className="traits__toggle"><input type="checkbox" checked={onlyChanged} onChange={(e) => setOnlyChanged(e.target.checked)} /> Changed or known only</label>
              <table className="diff">
                <thead><tr><th>Trait</th><th>A</th><th>B</th></tr></thead>
                <tbody>
                  {diff.filter((d) => !onlyChanged || d.changed || d.known).map((d) => (
                    <tr key={d.key} className={d.changed ? 'is-changed' : ''}>
                      <td>{d.label}</td><td>{d.a}</td><td>{d.b}</td>
                    </tr>
                  ))}
                  <tr className={JSON.stringify(revA.profile.marks) !== JSON.stringify(revB.profile.marks) ? 'is-changed' : ''}>
                    <td>Marks</td>
                    <td>{revA.profile.marks?.map(markLabel).join('; ') || '—'}</td>
                    <td>{revB.profile.marks?.map(markLabel).join('; ') || '—'}</td>
                  </tr>
                  {adjDiff.map((x) => (
                    <tr key={x.label} className="is-changed"><td>{x.label}</td><td className="mono">{x.a.toFixed(2)}</td><td className="mono">{x.b.toFixed(2)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      ) : (
        <div className="skeleton" style={{ height: 480 }} />
      )}
    </div>
  )
}
