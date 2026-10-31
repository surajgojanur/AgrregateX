import { useMemo } from 'react'
import { optionLabel } from '../../lib/format'
import { useApp } from '../../state/AppContext'
import Icon from '../ui/Icon'

// Quick categorical controls that the spec calls out, placed above the sliders.
const QUICK = ['face_shape', 'chin', 'hair_style', 'hairline', 'eye_shape', 'facial_hair']

const AdjustPanel = ({ profile, onChange, aiNotice }) => {
  const { catalog } = useApp()
  const groups = useMemo(() => {
    const g = {}
    for (const a of catalog.adjustments) (g[a.group] ||= []).push(a)
    return g
  }, [catalog])
  const traitByKey = Object.fromEntries(catalog.traits.map((t) => [t.key, t]))

  const setAdj = (key, value) => {
    const next = structuredClone(profile)
    if (Math.abs(value) < 0.001) delete next.adjustments[key]
    else next.adjustments[key] = Math.round(value * 100) / 100
    onChange(next, `adj:${key}`)
  }

  const setTrait = (key, value) => {
    const next = structuredClone(profile)
    next.traits[key] = value
      ? { value, source: 'manual', evidence: null, certainty: 'stated', alternatives: [] }
      : { value: null, source: 'unknown', evidence: null, certainty: 'stated', alternatives: [] }
    onChange(next, `trait:${key}`)
  }

  const changed = Object.keys(profile.adjustments || {}).length

  return (
    <div className="adjust">
      {aiNotice && (
        <div className="alert alert--warn">
          <Icon name="info" />
          <span>{aiNotice}</span>
        </div>
      )}
      <section className="adjust__group">
        <h3 className="label">Feature shapes</h3>
        <div className="adjust__quick">
          {QUICK.map((key) => {
            const t = traitByKey[key]
            return (
              <label key={key} className="field">
                <span className="adjust__name">{t.label}</span>
                <select className="select select--sm" value={profile.traits[key]?.value || ''} onChange={(e) => setTrait(key, e.target.value || null)}>
                  <option value="">Unknown (neutral)</option>
                  {t.options.map((o) => <option key={o} value={o}>{optionLabel(t, o)}</option>)}
                </select>
              </label>
            )
          })}
        </div>
      </section>

      {Object.entries(groups).map(([group, items]) => (
        <section key={group} className="adjust__group">
          <h3 className="label">{group}</h3>
          {items.map((a) => {
            const v = profile.adjustments?.[a.key] ?? 0
            return (
              <div key={a.key} className={`slider ${v !== 0 ? 'is-changed' : ''}`}>
                <div className="slider__top">
                  <label htmlFor={`adj-${a.key}`}>{a.label}</label>
                  <span className="mono slider__val">{v > 0 ? '+' : ''}{v.toFixed(2)}</span>
                  <button type="button" className="btn btn--ghost btn--icon btn--sm slider__reset" disabled={v === 0}
                    onClick={() => setAdj(a.key, 0)} aria-label={`Reset ${a.label}`}>
                    <Icon name="reset" />
                  </button>
                </div>
                <input
                  id={`adj-${a.key}`} type="range" className="range" min={-1} max={1} step={0.05} value={v}
                  style={{ '--fill': `${((v + 1) / 2) * 100}%` }}
                  onChange={(e) => setAdj(a.key, Number(e.target.value))}
                  onDoubleClick={() => setAdj(a.key, 0)}
                />
              </div>
            )
          })}
        </section>
      ))}
      <p className="field__hint">
        {changed} proportion{changed === 1 ? '' : 's'} adjusted. Sliders fine-tune the offline composite instantly; double-click a slider to reset it.
      </p>
    </div>
  )
}

export default AdjustPanel
