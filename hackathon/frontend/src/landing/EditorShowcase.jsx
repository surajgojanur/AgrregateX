import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import CompareSlider from '../components/sketch/CompareSlider'
import Icon from '../components/ui/Icon'
import { optionLabel } from '../lib/format'
import { useEngine } from './engine'
import { Reveal, SplitLines } from './motion'
import { matchSketch } from './sketches'

const SEED = 'An adult with an oval face, short dark hair, thick eyebrows, a narrow nose, and a small scar on the left cheek.'
// Traits the reference sketches vary in, so each button visibly changes the face.
const CONTROLS = ['facial_hair', 'eyewear', 'hair_style']

export default function EditorShowcase() {
  const { status, catalog, retry } = useEngine()
  const [profile, setProfile] = useState(null)
  const [current, setCurrent] = useState(null) // { url }
  const [revisions, setRevisions] = useState([]) // [{ n, url, profile }]
  const [compare, setCompare] = useState(false)
  const [error, setError] = useState(null)
  const started = useRef(false)

  const show = (p) => {
    const { url } = matchSketch(p)
    setCurrent({ url })
    return url
  }

  // Seed the showcase from the demo description once the engine is reachable.
  useEffect(() => {
    if (status !== 'online' || started.current) return
    started.current = true
    api.extract(SEED)
      .then((ex) => {
        setProfile(ex.profile)
        const url = show(ex.profile)
        setRevisions([{ n: 1, url, profile: ex.profile }])
      })
      .catch((err) => setError(err.message))
  }, [status])

  const change = (next) => {
    setProfile(next)
    show(next)
  }
  const setTrait = (key, value) => {
    const next = structuredClone(profile)
    next.traits[key] = { value, source: 'manual', evidence: null, certainty: 'stated', alternatives: [] }
    change(next)
  }

  const last = revisions[revisions.length - 1]
  const dirty = profile && last && JSON.stringify(last.profile) !== JSON.stringify(profile)
  const saveRevision = () => {
    if (!current || !dirty) return
    setRevisions((rs) => [...rs, { n: rs.length + 1, url: current.url, profile }])
  }
  const reset = () => {
    if (!revisions[0]) return
    setProfile(revisions[0].profile)
    setCurrent({ url: revisions[0].url })
  }

  const traitByKey = Object.fromEntries((catalog?.traits || []).map((t) => [t.key, t]))
  const known = profile ? Object.entries(profile.traits).filter(([, t]) => t.value) : []
  const before = dirty ? last : revisions[revisions.length - 2]

  return (
    <section id="editor" className="lp-section" aria-labelledby="editor-title">
      <div className="lp-shell">
        <div className="lp-section__head lp-section__head--split">
          <div>
            <Reveal><span className="lp-eyebrow">Interactive editor</span></Reveal>
            <SplitLines lines={['Every choice', 'changes the sketch.']} className="lp-h2" />
            <span id="editor-title" className="sr-only">Interactive editor showcase</span>
          </div>
          <Reveal delay={150}>
            <p className="lp-section__lead">
              Pick a trait and the closest pencil sketch from the reference set appears. Save revisions and compare them side by side.
              The full workspace adds undo and redo, saved history, and exports.
            </p>
          </Reveal>
        </div>

        <Reveal y={40} className="lp-editor">
          <div className="lp-editor__bar">
            <span className="lp-editor__dots" aria-hidden="true"><i /><i /><i /></span>
            <span className="lp-mono">RV-DEMO-0002</span>
            <span className="lp-tag lp-tag--ai">AI sketch · fictional</span>
            <span className="lp-mono lp-faint lp-editor__rev">
              {revisions.length ? `R${dirty ? `${last.n} + edits` : last.n}` : '—'} · demo only, not stored
            </span>
          </div>
          <div className="lp-editor__body">
            <div className="lp-editor__view">
              {compare && before && current ? (
                <div className="lp-editor__compare">
                  <CompareSlider before={before.url} after={current.url} beforeLabel={`R${before.n}`} afterLabel={dirty ? 'Current' : `R${last.n}`} />
                </div>
              ) : current ? (
                <img src={current.url} alt="Pencil reference sketch matching the selected traits" />
              ) : status === 'offline' ? (
                <div className="lp-demo__empty">
                  <Icon name="cpu" />
                  <strong>Live editor needs the local engine</strong>
                  <span>No backend is connected yet (preview mode).</span>
                  <button type="button" className="lp-btn lp-btn--ghost lp-btn--sm" onClick={retry}><Icon name="reset" /> Retry</button>
                </div>
              ) : (
                <div className="lp-skel" aria-busy="true" />
              )}
              {error && <p className="lp-error lp-editor__err" role="alert">{error}</p>}
            </div>

            <div className="lp-editor__panel">
              <div className="lp-editor__group">
                {CONTROLS.map((key) => {
                  const t = traitByKey[key]
                  if (!t) return null
                  return [
                    <span key={`${key}-l`} className="lp-label">{t.label}</span>,
                    <div key={key} className="lp-seg" role="group" aria-label={t.label}>
                      {t.options.map((o) => (
                        <button key={o} type="button" disabled={!profile} aria-pressed={profile?.traits[key]?.value === o}
                          onClick={() => setTrait(key, o)}>{optionLabel(t, o)}</button>
                      ))}
                    </div>,
                  ]
                })}
              </div>
              <div className="lp-editor__group">
                <span className="lp-label">Trait list</span>
                <ul className="lp-editor__traits">
                  {known.map(([k, t]) => (
                    <li key={k}><span>{traitByKey[k]?.label}</span><b>{optionLabel(traitByKey[k], t.value)}</b><i className={`lp-tag lp-tag--${t.source}`}>{t.source}</i></li>
                  ))}
                  {!known.length && <li className="lp-faint">—</li>}
                </ul>
              </div>
              <div className="lp-editor__actions">
                <button type="button" className="lp-btn lp-btn--ghost lp-btn--sm" onClick={saveRevision} disabled={!dirty}>
                  <Icon name="save" /> Save revision
                </button>
                <button type="button" className={`lp-btn lp-btn--sm ${compare ? 'lp-btn--primary' : 'lp-btn--ghost'}`}
                  onClick={() => setCompare((v) => !v)} disabled={!before} aria-pressed={compare}>
                  <Icon name="compare" /> Before / after
                </button>
                <button type="button" className="lp-btn lp-btn--ghost lp-btn--sm" onClick={reset} disabled={!revisions.length}>
                  <Icon name="reset" /> Reset
                </button>
              </div>
              <p className="lp-faint lp-editor__foot">
                Revisions here live only in this page. <a href="/app#/new">Open the workspace</a> to save them with full history.
              </p>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
