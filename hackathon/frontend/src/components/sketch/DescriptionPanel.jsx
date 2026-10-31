import { useMemo, useState } from 'react'
import { api } from '../../api/client'
import { optionLabel } from '../../lib/format'
import { useApp } from '../../state/AppContext'
import DictateButton from '../ui/DictateButton'
import Icon from '../ui/Icon'
import WitnessMerge from './WitnessMerge'

const EXAMPLES = [
  'An adult male with an oval face, short dark hair, thick eyebrows, a narrow nose, a small scar on the left cheek, and light facial hair.',
  'A woman in her late twenties with long wavy blonde hair, arched thin eyebrows, almond eyes, full lips and round glasses. Maybe a mole near her chin.',
  'Older man, balding with a receding hairline, bushy eyebrows, a hooked nose, large ears and a full beard. I don’t remember his eye colour.',
  'Teenage boy, spiky hair, round face, wide-set eyes, a button nose and freckles. He was not wearing glasses.',
]

const TABS = [
  { id: 'free', label: 'Description', icon: 'text' },
  { id: 'guided', label: 'Guided', icon: 'list' },
  { id: 'witnesses', label: 'Witnesses', icon: 'users' },
]

function GuidedForm({ catalog, onApply }) {
  const [answers, setAnswers] = useState({})
  const [mark, setMark] = useState({ type: '', location: 'left_cheek', size: 'small' })
  const [marks, setMarks] = useState([])
  const [observations, setObservations] = useState('')
  const groups = useMemo(() => {
    const g = {}
    for (const t of catalog.traits) (g[t.group] ||= []).push(t)
    return g
  }, [catalog])
  const answered = Object.values(answers).filter(Boolean).length
  const ageTrait = catalog.traits.find((t) => t.key === 'age_range')
  const ageIdx = answers.age_range ? ageTrait.options.indexOf(answers.age_range) + 1 : 0

  const set = (key, value) => setAnswers((a) => ({ ...a, [key]: value || null }))

  return (
    <div className="guided">
      <p className="muted guided__intro">
        Ask the witness one feature at a time. Leave anything they do not remember as <b>Unknown</b>. Unknown is never
        treated as “none”.
      </p>
      {Object.entries(groups).map(([group, traits]) => (
        <fieldset key={group} className="guided__group">
          <legend className="label">{group}</legend>
          {traits.map((t) => {
            if (t.key === 'age_range') {
              return (
                <div key={t.key} className="field">
                  <span className="guided__label">{t.label}</span>
                  <input
                    type="range" className="range" min={0} max={t.options.length} step={1} value={ageIdx}
                    style={{ '--fill': `${(ageIdx / t.options.length) * 100}%` }}
                    onChange={(e) => set(t.key, Number(e.target.value) ? t.options[Number(e.target.value) - 1] : null)}
                    aria-valuetext={optionLabel(t, answers.age_range)}
                  />
                  <span className="mono guided__value">{optionLabel(t, answers.age_range)}</span>
                </div>
              )
            }
            if (t.options.length <= 4) {
              return (
                <div key={t.key} className="field">
                  <span className="guided__label">{t.label}{t.rendered === 'recorded' && <span className="faint"> · recorded only</span>}</span>
                  <div className="segmented" role="group" aria-label={t.label}>
                    <button type="button" className="is-unknown" aria-pressed={!answers[t.key]} onClick={() => set(t.key, null)}>Unknown</button>
                    {t.options.map((o) => (
                      <button key={o} type="button" aria-pressed={answers[t.key] === o} onClick={() => set(t.key, o)}>{optionLabel(t, o)}</button>
                    ))}
                  </div>
                </div>
              )
            }
            return (
              <label key={t.key} className="field">
                <span className="guided__label">{t.label}{t.rendered === 'recorded' && <span className="faint"> · recorded only</span>}</span>
                <select className="select select--sm" value={answers[t.key] || ''} onChange={(e) => set(t.key, e.target.value)}>
                  <option value="">Unknown</option>
                  {t.options.map((o) => <option key={o} value={o}>{optionLabel(t, o)}</option>)}
                </select>
              </label>
            )
          })}
        </fieldset>
      ))}

      <fieldset className="guided__group">
        <legend className="label">Distinctive marks</legend>
        <div className="guided__mark">
          <select className="select select--sm" value={mark.type} onChange={(e) => setMark((m) => ({ ...m, type: e.target.value }))} aria-label="Mark type">
            <option value="">Type…</option>
            {catalog.marks.types.map((x) => <option key={x} value={x}>{optionLabel(null, x)}</option>)}
          </select>
          <select className="select select--sm" value={mark.location} onChange={(e) => setMark((m) => ({ ...m, location: e.target.value }))} aria-label="Location (subject's left/right)">
            {catalog.marks.locations.map((x) => <option key={x} value={x}>{optionLabel(null, x)}</option>)}
          </select>
          <select className="select select--sm" value={mark.size} onChange={(e) => setMark((m) => ({ ...m, size: e.target.value }))} aria-label="Size">
            {catalog.marks.sizes.map((x) => <option key={x} value={x}>{optionLabel(null, x)}</option>)}
          </select>
          <button type="button" className="btn btn--sm" disabled={!mark.type}
            onClick={() => { setMarks((ms) => [...ms, { ...mark }]); setMark((m) => ({ ...m, type: '' })) }}>
            <Icon name="plus" /> Add
          </button>
        </div>
        <span className="field__hint">Left/right refer to the subject’s left and right.</span>
        {marks.length > 0 && (
          <div className="chips">
            {marks.map((m, i) => (
              <button key={i} type="button" className="chip chip--cyan" onClick={() => setMarks((ms) => ms.filter((_, j) => j !== i))} title="Remove">
                {m.size} {m.type} · {m.location.replace(/_/g, ' ')} <Icon name="close" />
              </button>
            ))}
          </div>
        )}
      </fieldset>

      <label className="field">
        <span className="guided__label merge__wlabel">
          Additional observations
          <DictateButton value={observations} onChange={setObservations} maxLength={1000} />
        </span>
        <textarea className="textarea" rows={3} maxLength={1000} value={observations} onChange={(e) => setObservations(e.target.value)}
          placeholder="Clothing, posture, anything not covered above. Recorded in the report, not drawn." />
      </label>

      <button type="button" className="btn btn--primary btn--block" disabled={!answered && !marks.length && !observations.trim()}
        onClick={() => onApply({ answers, marks, observations })}>
        <Icon name="check" /> Apply {answered} answer{answered === 1 ? '' : 's'} to profile
      </button>
    </div>
  )
}

const DescriptionPanel = ({ description, onDescriptionChange, onExtracted, onGuided, onMerged }) => {
  const { catalog, notify } = useApp()
  const [tab, setTab] = useState('free')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const { description_min: min, description_max: max } = catalog.limits
  const len = description.trim().length
  const tooLong = description.length > max

  const extract = async () => {
    if (len < min) {
      setError(`Write at least ${min} characters describing the person.`)
      return
    }
    setError(null)
    setBusy(true)
    try {
      const result = await api.extract(description)
      onExtracted(result)
      if (!result.recognized_count) notify({ kind: 'warn', title: 'No traits recognised', message: 'Try the guided questions, or describe specific features.' })
      else notify({ kind: 'ok', title: `${result.recognized_count} characteristics extracted`, message: result.conflicts.length ? `${result.conflicts.length} conflict(s) need review.` : 'Review them in the profile panel.' })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel input-panel" aria-label="Witness input">
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} className="tabs__tab" onClick={() => setTab(t.id)}>
            <Icon name={t.icon} /> {t.label}
          </button>
        ))}
      </div>

      <div className="panel__body">
        {tab === 'free' && (
          <div className={`describe ${busy ? 'is-extracting' : ''}`}>
            <label className="field">
              <span className="label">Witness description</span>
              <textarea
                className="textarea describe__text"
                rows={8}
                value={description}
                onChange={(e) => { onDescriptionChange(e.target.value); if (error) setError(null) }}
                placeholder="Describe the face in the witness’s own words. Mention only what they actually remember."
                aria-invalid={Boolean(error) || tooLong}
                aria-describedby="describe-meta"
                onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') extract() }}
              />
              <span className="describe__progress" aria-hidden="true" />
            </label>
            <span className="sr-only" role="status">{busy ? 'Extracting traits from the description' : ''}</span>
            <div id="describe-meta" className="describe__meta">
              <span className={`mono ${tooLong ? 'text-red' : len && len < min ? 'text-amber' : 'faint'}`}>{description.length} / {max}</span>
              <span className="describe__actions">
                <DictateButton value={description} onChange={(v) => { onDescriptionChange(v); if (error) setError(null) }} maxLength={max} />
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => { onDescriptionChange(''); setError(null) }} disabled={!description}>
                  <Icon name="close" /> Clear
                </button>
              </span>
            </div>
            {error && <p className="field__error" role="alert">{error}</p>}

            {!description && (
              <div className="describe__examples">
                <span className="label">Example descriptions</span>
                {EXAMPLES.map((ex) => (
                  <button key={ex} type="button" className="example" onClick={() => onDescriptionChange(ex)}>
                    <Icon name="text" /> <span>{ex}</span>
                  </button>
                ))}
              </div>
            )}

            <button type="button" className="btn btn--primary btn--block btn--lg" onClick={extract} disabled={busy || tooLong || !description.trim()}>
              {busy ? <span className="spinner" /> : <Icon name="scan" />}
              {busy ? 'Extracting traits…' : 'Extract facial traits'}
              <span className="kbd mono">⌘↵</span>
            </button>
            <p className="field__hint">Runs locally with deterministic rules. Nothing is guessed: unmentioned features stay unknown.</p>
          </div>
        )}
        {tab === 'guided' && <GuidedForm catalog={catalog} onApply={onGuided} />}
        {tab === 'witnesses' && <WitnessMerge onApply={onMerged} />}
      </div>
    </section>
  )
}

export default DescriptionPanel
