import { useMemo, useState } from 'react'
import { optionLabel } from '../../lib/format'
import { useApp } from '../../state/AppContext'
import Icon from '../ui/Icon'

const SOURCE_LABEL = { described: 'Described', extracted: 'Extracted', manual: 'Manual', unknown: 'Unknown' }
const RENDER_HINT = {
  full: { icon: 'eye', title: 'Drawn in the offline composite' },
  tone: { icon: 'eye', title: 'Drawn as a monochrome tone only' },
  recorded: { icon: 'eyeOff', title: 'Recorded in the profile and report, not drawn' },
}

export const SourceTag = ({ tv }) => {
  if (tv?.alternatives?.length) return <span className="tag tag--conflict">Conflict</span>
  const src = tv?.value ? tv.source : 'unknown'
  return (
    <span className="trait__tags">
      <span className={`tag tag--${src}`}>{SOURCE_LABEL[src]}</span>
      {tv?.value && tv.certainty === 'uncertain' && <span className="tag tag--uncertain" title="Witness hedged this statement">Uncertain</span>}
    </span>
  )
}

// One visual state per row, in priority order, mirroring the tags shown in SourceTag.
const rowState = (tv) => (tv?.alternatives?.length ? 'conflict'
  : !tv?.value ? 'unknown'
    : tv.certainty === 'uncertain' ? 'uncertain'
      : tv.source)

const TraitRow = ({ trait, tv, onSet }) => {
  const conflict = tv?.alternatives?.length > 0
  const hint = RENDER_HINT[trait.rendered]
  return (
    <li className={`trait ${conflict ? 'is-conflict' : ''} ${tv?.value ? 'is-known' : ''} state-${rowState(tv)}`}>
      <div className="trait__top">
        <span className="trait__label">
          {trait.label}
          <span className={`trait__render is-${trait.rendered}`} title={hint.title}><Icon name={hint.icon} /></span>
        </span>
        <SourceTag tv={tv} />
      </div>
      <select
        className="select select--sm"
        value={tv?.value || ''}
        onChange={(e) => onSet(trait.key, e.target.value || null)}
        aria-label={trait.label}
      >
        <option value="">{conflict ? 'Unresolved conflict' : 'Unknown'}</option>
        {trait.options.map((o) => <option key={o} value={o}>{optionLabel(trait, o)}</option>)}
      </select>
      {conflict && (
        <div className="trait__conflict">
          <span className="text-amber">Witness statements disagree:</span>
          {tv.alternatives.map((alt) => (
            <button key={alt} type="button" className="chip chip--amber" onClick={() => onSet(trait.key, alt)}>
              Use {optionLabel(trait, alt)}
            </button>
          ))}
        </div>
      )}
      {tv?.evidence && tv.source !== 'manual' && <p className="trait__evidence mono" title={tv.evidence}>“{tv.evidence}”</p>}
    </li>
  )
}

const TraitPanel = ({ profile, onChange, revealKey = 0 }) => {
  const { catalog } = useApp()
  const [showUnknown, setShowUnknown] = useState(true)
  const groups = useMemo(() => {
    const g = {}
    for (const t of catalog.traits) (g[t.group] ||= []).push(t)
    return g
  }, [catalog])

  const setTrait = (key, value) => {
    const next = structuredClone(profile)
    next.traits[key] = value
      ? { value, source: 'manual', evidence: null, certainty: 'stated', alternatives: [] }
      : { value: null, source: 'unknown', evidence: null, certainty: 'stated', alternatives: [] }
    onChange(next, `trait:${key}`)
  }

  const setMark = (i, patch, key) => {
    const next = structuredClone(profile)
    next.marks[i] = { ...next.marks[i], ...patch, source: 'manual' }
    onChange(next, key)
  }

  const addMark = () => {
    const next = structuredClone(profile)
    next.marks.push({ id: `m${Date.now().toString(36)}`, type: 'scar', location: 'left_cheek', size: 'small', dx: 0, dy: 0, side_specified: true, source: 'manual' })
    onChange(next, 'marks:add')
  }

  const removeMark = (i) => {
    const next = structuredClone(profile)
    next.marks.splice(i, 1)
    onChange(next, 'marks:remove')
  }

  const counts = catalog.traits.reduce((acc, t) => {
    const tv = profile.traits[t.key]
    if (tv?.alternatives?.length) acc.conflict += 1
    else if (tv?.value) acc.known += 1
    else acc.unknown += 1
    return acc
  }, { known: 0, unknown: 0, conflict: 0 })

  return (
    <div className="traits">
      <div className="traits__summary">
        <span className="chip chip--cyan"><span className="mono">{counts.known}</span> known</span>
        <span className="chip"><span className="mono">{counts.unknown}</span> unknown</span>
        {counts.conflict > 0 && <span className="chip chip--amber"><span className="mono">{counts.conflict}</span> conflict</span>}
        <label className="traits__toggle">
          <input type="checkbox" checked={showUnknown} onChange={(e) => setShowUnknown(e.target.checked)} /> Show unknown
        </label>
      </div>

      {Object.entries(groups).map(([group, traits], groupIndex) => {
        const visible = traits.filter((t) => showUnknown || profile.traits[t.key]?.value || profile.traits[t.key]?.alternatives?.length)
        if (!visible.length) return null
        return (
          <section key={group} className="traits__group" style={{ '--g': groupIndex }}>
            <h3 className="label">{group}</h3>
            <ul className="traits__list" key={revealKey}>
              {visible.map((t) => <TraitRow key={t.key} trait={t} tv={profile.traits[t.key]} onSet={setTrait} />)}
            </ul>
          </section>
        )
      })}

      <section className="traits__group">
        <h3 className="label traits__markhead">
          Distinctive marks
          <button type="button" className="btn btn--ghost btn--sm" onClick={addMark}><Icon name="plus" /> Add mark</button>
        </h3>
        {profile.marks.length === 0 ? (
          <p className="faint traits__none">None recorded.</p>
        ) : (
          <ul className="marks">
            {profile.marks.map((m, i) => (
              <li key={m.id} className="mark">
                <div className="mark__row">
                  <select className="select select--sm" value={m.type} onChange={(e) => setMark(i, { type: e.target.value }, `mark:${m.id}:type`)} aria-label="Mark type">
                    {catalog.marks.types.map((x) => <option key={x} value={x}>{optionLabel(null, x)}</option>)}
                  </select>
                  <select className="select select--sm" value={m.size} onChange={(e) => setMark(i, { size: e.target.value }, `mark:${m.id}:size`)} aria-label="Mark size">
                    {catalog.marks.sizes.map((x) => <option key={x} value={x}>{optionLabel(null, x)}</option>)}
                  </select>
                  <button type="button" className="btn btn--ghost btn--icon btn--sm" onClick={() => removeMark(i)} aria-label="Remove mark"><Icon name="trash" /></button>
                </div>
                <select className="select select--sm" value={m.location}
                  onChange={(e) => setMark(i, { location: e.target.value, side_specified: true }, `mark:${m.id}:loc`)} aria-label="Mark location">
                  {catalog.marks.locations.map((x) => <option key={x} value={x}>{optionLabel(null, x)} (subject’s)</option>)}
                </select>
                {m.side_specified === false && <span className="tag tag--uncertain">Side not stated</span>}
                <div className="mark__pos">
                  <label><span className="label">Position X</span>
                    <input type="range" className="range" min={-1} max={1} step={0.05} value={m.dx}
                      style={{ '--fill': `${((m.dx + 1) / 2) * 100}%` }}
                      onChange={(e) => setMark(i, { dx: Number(e.target.value) }, `mark:${m.id}:dx`)} />
                  </label>
                  <label><span className="label">Position Y</span>
                    <input type="range" className="range" min={-1} max={1} step={0.05} value={m.dy}
                      style={{ '--fill': `${((m.dy + 1) / 2) * 100}%` }}
                      onChange={(e) => setMark(i, { dy: Number(e.target.value) }, `mark:${m.id}:dy`)} />
                  </label>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="traits__group">
        <h3 className="label">Additional observations</h3>
        <textarea className="textarea" rows={3} maxLength={1000} value={profile.observations || ''}
          onChange={(e) => onChange({ ...profile, observations: e.target.value }, 'observations')}
          placeholder="Recorded in the report. Not drawn." />
      </section>
    </div>
  )
}

export default TraitPanel
