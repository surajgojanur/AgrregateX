import { useState } from 'react'
import { api } from '../../api/client'
import { optionLabel } from '../../lib/format'
import { useApp } from '../../state/AppContext'
import DictateButton from '../ui/DictateButton'
import Icon from '../ui/Icon'

const EXAMPLES = [
  'Make the eyebrows thicker',
  'Change the face shape to oval',
  'Add a small scar on the left cheek',
  'Make the hairline receding',
  'Make the jaw narrower',
]

// 1) parse → 2) operator reviews/edits proposed changes → 3) apply to profile.
const RefinePanel = ({ profile, onApply }) => {
  const { catalog, notify } = useApp()
  const [text, setText] = useState('')
  const [proposal, setProposal] = useState(null)
  const [selected, setSelected] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const traitByKey = Object.fromEntries(catalog.traits.map((t) => [t.key, t]))

  const parse = async (instruction = text) => {
    if (instruction.trim().length < 3) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.parseRefine(instruction.trim(), profile)
      setProposal(res)
      setSelected(Object.fromEntries(res.changes.map((c) => [c.id, true])))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const editTarget = (id, to) => {
    setProposal((p) => ({
      ...p,
      changes: p.changes.map((c) => (c.id === id ? { ...c, to, to_label: optionLabel(traitByKey[c.key], to) } : c)),
    }))
  }

  const apply = async () => {
    const chosen = proposal.changes.filter((c) => selected[c.id])
    if (!chosen.length) return
    setBusy(true)
    try {
      const res = await api.applyRefine(profile, chosen)
      onApply(res.profile, chosen)
      notify({ kind: 'ok', title: `${chosen.length} change${chosen.length > 1 ? 's' : ''} applied to the profile`, message: 'The preview re-renders from the updated profile. Save a revision to keep it.' })
      setProposal(null)
      setText('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const count = proposal ? proposal.changes.filter((c) => selected[c.id]).length : 0

  return (
    <div className="refine">
      <form className="refine__form" onSubmit={(e) => { e.preventDefault(); parse() }}>
        <label className="field">
          <span className="label refine__label">
            Refinement request
            <DictateButton value={text} onChange={setText} maxLength={500} />
          </span>
          <input className="input" value={text} onChange={(e) => setText(e.target.value)} maxLength={500}
            placeholder="e.g. make the eyebrows thicker and the jaw narrower" />
        </label>
        <button type="submit" className="btn btn--blue" disabled={busy || text.trim().length < 3}>
          {busy && !proposal ? <span className="spinner" /> : <Icon name="wand" />} Interpret
        </button>
      </form>
      <div className="chips refine__examples">
        {EXAMPLES.map((ex) => (
          <button key={ex} type="button" className="chip" onClick={() => { setText(ex); parse(ex) }}>{ex}</button>
        ))}
      </div>
      <p className="field__hint">Parsed locally with deterministic rules. Nothing changes until you confirm.</p>
      {error && <p className="field__error" role="alert">{error}</p>}

      {proposal && (
        <div className="refine__proposal reveal">
          {proposal.changes.length > 0 ? (
            <>
              <span className="label">Proposed changes</span>
              <ul className="changes">
                {proposal.changes.map((c) => (
                  <li key={c.id} className={`change ${selected[c.id] ? 'is-on' : ''}`}>
                    <input type="checkbox" checked={Boolean(selected[c.id])} aria-label={`Include ${c.label}`}
                      onChange={(e) => setSelected((s) => ({ ...s, [c.id]: e.target.checked }))} />
                    <div className="change__body">
                      <strong>{c.label}</strong>
                      <div className="change__diff mono">
                        <span className="change__from">{c.from_label}</span>
                        <Icon name="arrowRight" />
                        {c.kind === 'trait' ? (
                          <select className="select select--sm" value={c.to || ''} onChange={(e) => editTarget(c.id, e.target.value)} aria-label={`New value for ${c.label}`}>
                            {traitByKey[c.key].options.map((o) => <option key={o} value={o}>{optionLabel(traitByKey[c.key], o)}</option>)}
                          </select>
                        ) : (
                          <span className="change__to">{c.to_label}</span>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <div className="alert alert--warn"><Icon name="alert" /><span>{proposal.message || 'Nothing to change.'}</span></div>
          )}
          {proposal.already?.map((a) => <p key={a} className="faint refine__note"><Icon name="check" /> {a}</p>)}
          {proposal.unrecognized?.length > 0 && (
            <p className="text-amber refine__note"><Icon name="alert" /> Not understood: “{proposal.unrecognized.join('”, “')}”</p>
          )}
          <div className="refine__actions">
            <button type="button" className="btn btn--ghost" onClick={() => setProposal(null)}>Discard</button>
            <button type="button" className="btn btn--primary" disabled={!count || busy} onClick={apply}>
              {busy ? <span className="spinner" /> : <Icon name="check" />} Apply {count} change{count === 1 ? '' : 's'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default RefinePanel
