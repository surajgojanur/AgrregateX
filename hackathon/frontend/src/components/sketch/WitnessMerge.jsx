import { useState } from 'react'
import { api } from '../../api/client'
import { optionLabel } from '../../lib/format'
import { useApp } from '../../state/AppContext'
import DictateButton from '../ui/DictateButton'
import Icon from '../ui/Icon'

const STATUS = {
  shared: { label: 'Shared', cls: 'chip--green' },
  conflicting: { label: 'Conflicting', cls: 'chip--amber' },
  single_source: { label: 'Single source', cls: 'chip--blue' },
  unmentioned: { label: 'Unmentioned', cls: '' },
}

// Multiple independent descriptions → shared / conflicting / single-source /
// unmentioned. Conflicts must be decided by the operator before applying.
const WitnessMerge = ({ onApply }) => {
  const { catalog } = useApp()
  const [texts, setTexts] = useState(['', ''])
  const [result, setResult] = useState(null)
  const [decisions, setDecisions] = useState({})
  const [filter, setFilter] = useState('all')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const traitByKey = Object.fromEntries(catalog.traits.map((t) => [t.key, t]))

  const compare = async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await api.merge(texts.map((t) => t.trim()).filter(Boolean))
      setResult(r)
      setDecisions({})
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const pending = result ? result.requires_review.filter((k) => !(k in decisions)) : []

  const apply = () => {
    const profile = structuredClone(result.combined_profile)
    for (const [key, value] of Object.entries(decisions)) {
      profile.traits[key] = value
        ? { value, source: 'manual', evidence: 'Operator resolved a witness conflict', certainty: 'stated', alternatives: [] }
        : { value: null, source: 'unknown', evidence: 'Operator left the conflict unresolved', certainty: 'stated', alternatives: [] }
    }
    const description = result.witnesses.map((w) => `Witness ${w.index}: ${w.description}`).join('\n')
    onApply({ profile, description })
  }

  const rows = result ? result.traits.filter((r) => (filter === 'all' ? r.status !== 'unmentioned' : r.status === filter)) : []

  return (
    <div className="merge">
      <p className="muted">Enter each witness’s account separately. Revelio compares them trait by trait and never resolves disagreements for you.</p>
      {texts.map((t, i) => (
        <label key={i} className="field">
          <span className="label merge__wlabel">
            Witness {i + 1}
            <span className="describe__actions">
              <DictateButton value={t} maxLength={2000}
                onChange={(v) => setTexts((ts) => ts.map((x, j) => (j === i ? v : x)))} />
              {texts.length > 2 && (
                <button type="button" className="btn btn--ghost btn--sm btn--icon" aria-label={`Remove witness ${i + 1}`}
                  onClick={() => setTexts((ts) => ts.filter((_, j) => j !== i))}>
                  <Icon name="close" />
                </button>
              )}
            </span>
          </span>
          <textarea className="textarea" rows={3} maxLength={2000} value={t}
            onChange={(e) => setTexts((ts) => ts.map((x, j) => (j === i ? e.target.value : x)))}
            placeholder="This witness’s description…" />
        </label>
      ))}
      <div className="merge__actions">
        <button type="button" className="btn btn--sm" disabled={texts.length >= 4} onClick={() => setTexts((ts) => [...ts, ''])}>
          <Icon name="plus" /> Add witness
        </button>
        <button type="button" className="btn btn--primary btn--sm" onClick={compare}
          disabled={busy || texts.filter((t) => t.trim().length >= 10).length < 2}>
          {busy ? <span className="spinner" /> : <Icon name="compare" />} Compare descriptions
        </button>
      </div>
      {error && <p className="field__error" role="alert">{error}</p>}

      {result && (
        <div className="merge__result reveal">
          <div className="merge__counts">
            {['all', 'shared', 'conflicting', 'single_source', 'unmentioned'].map((s) => (
              <button key={s} type="button" className={`chip ${filter === s ? 'chip--cyan' : ''}`} onClick={() => setFilter(s)}>
                {s === 'all' ? 'Mentioned' : STATUS[s].label} <span className="mono">{s === 'all' ? result.traits.length - result.counts.unmentioned : result.counts[s]}</span>
              </button>
            ))}
          </div>
          <ul className="merge__rows">
            {rows.map((r) => (
              <li key={r.key} className={`merge__row is-${r.status}`}>
                <div className="merge__head">
                  <strong>{r.label}</strong>
                  <span className={`chip ${STATUS[r.status].cls}`}>{STATUS[r.status].label}</span>
                </div>
                {r.mentions.length > 0 && (
                  <div className="merge__mentions">
                    {r.mentions.map((m, i) => (
                      <span key={i} className="mono merge__mention" title={m.evidence || ''}>
                        W{m.witness}: {m.label}{m.certainty === 'uncertain' ? '?' : ''}
                      </span>
                    ))}
                  </div>
                )}
                {r.status === 'conflicting' && (
                  <div className="merge__decide" role="radiogroup" aria-label={`Resolve ${r.label}`}>
                    {r.combined.alternatives.map((alt) => (
                      <button key={alt} type="button" className={`chip ${decisions[r.key] === alt ? 'chip--cyan' : ''}`}
                        aria-pressed={decisions[r.key] === alt} onClick={() => setDecisions((d) => ({ ...d, [r.key]: alt }))}>
                        Use {optionLabel(traitByKey[r.key], alt)}
                      </button>
                    ))}
                    <button type="button" className={`chip ${r.key in decisions && decisions[r.key] === null ? 'chip--cyan' : ''}`}
                      onClick={() => setDecisions((d) => ({ ...d, [r.key]: null }))}>
                      Leave unknown
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
          {result.marks.length > 0 && (
            <div className="merge__marks">
              <span className="label">Distinctive marks</span>
              {result.marks.map((m, i) => (
                <span key={i} className={`chip ${m.status === 'shared' ? 'chip--green' : 'chip--blue'}`}>
                  {m.type} · {m.location.replace(/_/g, ' ')} · W{m.witnesses.join(', W')}
                </span>
              ))}
            </div>
          )}
          <div className="alert alert--info"><Icon name="info" /><span>{result.disclaimer}</span></div>
          <button type="button" className="btn btn--primary btn--block" disabled={pending.length > 0} onClick={apply}>
            <Icon name="check" />
            {pending.length ? `Resolve ${pending.length} conflict${pending.length > 1 ? 's' : ''} to continue` : 'Apply combined profile'}
          </button>
        </div>
      )}
    </div>
  )
}

export default WitnessMerge
