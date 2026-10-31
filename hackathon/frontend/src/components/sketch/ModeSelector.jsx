import { useApp } from '../../state/AppContext'
import Icon from '../ui/Icon'

const ICONS = { offline: 'cpu', local: 'layers', hosted: 'cloud' }

const ModeSelector = ({ mode, onChange }) => {
  const { providers } = useApp()
  return (
    <section className="panel modes" aria-labelledby="mode-title">
      <div className="panel__head">
        <h2 id="mode-title" className="panel__title section-title">Generation method</h2>
      </div>
      <div className="modes__list" role="radiogroup" aria-labelledby="mode-title">
        {['offline', 'local', 'hosted'].map((id) => {
          const p = providers[id]
          if (!p) return null
          const selected = mode === id
          return (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={!p.available}
              className={`mode ${selected ? 'is-selected' : ''}`}
              onClick={() => onChange(id)}
            >
              <span className="mode__icon"><Icon name={ICONS[id]} /></span>
              <span className="mode__text">
                <span className="mode__name">
                  {p.label}
                  <span className={`tag ${p.runs_locally ? 'tag--local' : 'tag--remote'}`}>{p.runs_locally ? 'Local' : 'Remote'}</span>
                  {p.kind === 'ai' && <span className="tag tag--ai">AI</span>}
                </span>
                <span className="mode__reason">{p.reason}</span>
              </span>
              <span className={`dot ${p.available ? 'dot--ok' : 'dot--idle'}`} aria-label={p.available ? 'available' : 'unavailable'} />
            </button>
          )
        })}
      </div>
    </section>
  )
}

export default ModeSelector
