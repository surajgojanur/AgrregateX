import { useState } from 'react'
import { api } from '../api/client'
import Icon from '../components/ui/Icon'
import { downloadBlob, optionLabel } from '../lib/format'
import { useEngine } from './engine'
import { Reveal, SplitLines } from './motion'
import { matchSketch } from './sketches'

const DEFAULT_DESCRIPTION =
  'An adult with an oval face, short dark hair, thick eyebrows, a narrow nose, and a small scar on the left cheek.'
// Traits the reference sketches vary in, so each control visibly changes the face.
const CONTROLS = ['facial_hair', 'eyewear', 'hair_style', 'hair_length']

export default function LiveDemo() {
  const { status, catalog, retry } = useEngine()
  const [description, setDescription] = useState(DEFAULT_DESCRIPTION)
  const [profile, setProfile] = useState(null)
  const [extraction, setExtraction] = useState(null)
  const [phase, setPhase] = useState('idle') // idle | extracting | ready
  const [inputError, setInputError] = useState(null)
  const [preview, setPreview] = useState(null) // url of the matched sketch
  const [renders, setRenders] = useState(0)
  const [downloading, setDownloading] = useState(false)

  const render = (p) => {
    setPreview(matchSketch(p).url)
    setRenders((n) => n + 1)
  }

  const traitByKey = Object.fromEntries((catalog?.traits || []).map((t) => [t.key, t]))
  const offline = status === 'offline'

  const generate = async () => {
    setInputError(null)
    if (description.trim().length < 10) {
      setInputError('Write at least 10 characters describing the (fictional) face.')
      return
    }
    setPhase('extracting')
    try {
      const ex = await api.extract(description.trim())
      setExtraction(ex)
      setProfile(ex.profile)
      render(ex.profile)
      setPhase('ready')
    } catch (err) {
      setInputError(err.message)
      setPhase(profile ? 'ready' : 'idle')
    }
  }

  const update = (next) => {
    setProfile(next)
    render(next)
  }

  const setTrait = (key, value) => {
    const next = structuredClone(profile)
    next.traits[key] = value
      ? { value, source: 'manual', evidence: null, certainty: 'stated', alternatives: [] }
      : { value: null, source: 'unknown', evidence: null, certainty: 'stated', alternatives: [] }
    update(next)
  }

  const download = async () => {
    setDownloading(true)
    try {
      const res = await fetch(preview)
      if (!res.ok) throw new Error('Could not download the sketch.')
      downloadBlob(await res.blob(), 'revelio-demo-sketch.webp')
    } catch (err) {
      setInputError(err.message)
    } finally {
      setDownloading(false)
    }
  }

  const known = profile ? Object.entries(profile.traits).filter(([, t]) => t.value) : []
  const unknownCount = profile ? Object.values(profile.traits).filter((t) => !t.value && !t.alternatives?.length).length : 0

  return (
    <section id="demo" className="lp-section lp-demo" aria-labelledby="demo-title">
      <div className="lp-shell">
        <div className="lp-section__head">
          <Reveal><span className="lp-eyebrow">Live demo · runs on the local engine</span></Reveal>
          <SplitLines lines={['Describe a face.', 'Watch it become a composite.']} className="lp-h2" />
          <span id="demo-title" className="sr-only">Live demo</span>
          <Reveal delay={150}>
            <p className="lp-section__lead">
              This demo uses the workspace’s trait extractor, then shows the closest pencil sketch from a fictional reference set. Use a fictional description; nothing is saved.
            </p>
          </Reveal>
        </div>

        <Reveal className="lp-demo__panel" y={36}>
          <div className="lp-demo__input">
            <label className="lp-label" htmlFor="demo-desc">Fictional description</label>
            <textarea id="demo-desc" className="lp-textarea" rows={5} maxLength={2000} value={description}
              onChange={(e) => { setDescription(e.target.value); setInputError(null) }}
              aria-invalid={Boolean(inputError)} />
            <div className="lp-demo__row">
              <span className="lp-mono lp-faint">{description.length} / 2000</span>
              <button type="button" className="lp-link" onClick={() => setDescription(DEFAULT_DESCRIPTION)}>Reset example</button>
            </div>
            {inputError && <p className="lp-error" role="alert">{inputError}</p>}
            <button type="button" className="lp-btn lp-btn--primary lp-btn--block" onClick={generate}
              disabled={offline || phase === 'extracting' || status === 'checking'}>
              {phase === 'extracting' ? <span className="lp-spinner" /> : <Icon name="scan" />}
              {phase === 'extracting' ? 'Extracting traits…' : profile ? 'Regenerate from description' : 'Generate Composite'}
            </button>

            {extraction && (
              <div className="lp-demo__extract">
                <span className="lp-label">Extracted traits <span className="lp-mono lp-faint">{known.length} known · {unknownCount} unknown</span></span>
                <ul className="lp-chips">
                  {known.map(([k, t]) => (
                    <li key={k} className={`lp-chip lp-chip--${t.source}`}>
                      {traitByKey[k]?.label}: <b>{optionLabel(traitByKey[k], t.value)}</b>
                    </li>
                  ))}
                  {profile.marks.map((m) => (
                    <li key={m.id} className={`lp-chip lp-chip--${m.source}`}>{m.size} {m.type} · {m.location.replace(/_/g, ' ')}</li>
                  ))}
                </ul>
                {extraction.conflicts.length > 0 && (
                  <p className="lp-warn"><Icon name="alert" /> {extraction.conflicts.length} conflicting statement(s) left unresolved, as in the workspace.</p>
                )}
              </div>
            )}
          </div>

          <div className="lp-demo__stage">
            <div className="lp-demo__label">
              <span className="lp-tag lp-tag--ai">Closest reference sketch · AI-generated</span>
              <span className="lp-mono lp-faint">{renders ? `match #${renders}` : 'no match yet'}</span>
            </div>
            <div className="lp-demo__frame">
              {preview ? (
                <img src={preview} alt="Pencil reference sketch closest to the description above" />
              ) : offline ? (
                <div className="lp-demo__empty">
                  <Icon name="cpu" />
                  <strong>The local engine isn’t running</strong>
                  <span>The live demo needs a backend, and none is connected yet (preview mode).</span>
                  <button type="button" className="lp-btn lp-btn--ghost lp-btn--sm" onClick={retry}><Icon name="reset" /> Retry</button>
                </div>
              ) : (
                <div className="lp-demo__empty">
                  <Icon name="scan" />
                  <strong>Ready when you are</strong>
                  <span>Click <b>Generate Composite</b> to extract traits and show the closest pencil sketch.</span>
                </div>
              )}
            </div>
            <p className="lp-demo__note">
              The sketch is matched on facial hair, eyewear, hair and scars from a small set of fictional AI-generated references. It is an illustration of the workflow, not a likeness of anyone described.
            </p>
            <button type="button" className="lp-btn lp-btn--ghost lp-btn--block" onClick={download} disabled={!preview || downloading}>
              {downloading ? <span className="lp-spinner" /> : <Icon name="download" />} Download sketch
            </button>
          </div>

          <div className="lp-demo__controls" aria-label="Adjust supported characteristics">
            <span className="lp-label">Adjust supported characteristics</span>
            {!profile ? (
              <p className="lp-faint lp-demo__hint">Generate a composite first. Each control below picks the closest matching sketch.</p>
            ) : (
              <>
                <div className="lp-demo__selects">
                  {CONTROLS.map((key) => {
                    const t = traitByKey[key]
                    if (!t) return null
                    return (
                      <label key={key} className="lp-field">
                        <span>{t.label}</span>
                        <select className="lp-select" value={profile.traits[key]?.value || ''} onChange={(e) => setTrait(key, e.target.value || null)}>
                          <option value="">Unknown (neutral)</option>
                          {t.options.map((o) => <option key={o} value={o}>{optionLabel(t, o)}</option>)}
                        </select>
                      </label>
                    )
                  })}
                </div>
              </>
            )}
          </div>
        </Reveal>
      </div>
    </section>
  )
}
