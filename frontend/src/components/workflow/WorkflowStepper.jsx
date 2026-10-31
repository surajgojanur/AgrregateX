import Icon from '../ui/Icon'

const STATE_TEXT = { done: 'completed', current: 'current step', active: 'in progress', pending: 'pending', blocked: 'blocked', error: 'error' }

/**
 * Compact case workflow. Each step carries its own state, derived by the caller from
 * saved case data; `onSelect` moves to that step's section when it is reachable.
 */
export default function WorkflowStepper({ steps, label = 'Case workflow' }) {
  return (
    <nav className="wflow" aria-label={label}>
      <ol className="wflow__list">
        {steps.map((s, i) => {
          const reachable = s.onSelect && s.state !== 'blocked'
          const node = (
            <>
              <span className="wflow__node" aria-hidden="true">
                {s.state === 'done' ? <Icon name="check" strokeWidth={2.4} />
                  : s.state === 'error' ? <Icon name="alert" />
                    : s.state === 'blocked' ? <Icon name="lock" />
                      : <span className="mono">{i + 1}</span>}
              </span>
              <span className="wflow__text">
                <span className="wflow__label">{s.label}</span>
                <span className="wflow__detail">{s.detail}</span>
              </span>
              <span className="sr-only">, {STATE_TEXT[s.state]}</span>
            </>
          )
          return (
            <li key={s.id} className={`wflow__step is-${s.state}`} aria-current={s.state === 'current' || s.state === 'active' ? 'step' : undefined}>
              {reachable
                ? <button type="button" className="wflow__item" onClick={s.onSelect} title={s.detail}>{node}</button>
                : <div className="wflow__item" title={s.detail}>{node}</div>}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
