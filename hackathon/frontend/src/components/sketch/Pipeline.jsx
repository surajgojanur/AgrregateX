import Icon from '../ui/Icon'

/** Evidence-processing pipeline — every step reflects actual editor state. */
const Pipeline = ({ steps }) => (
  <ol className="pipeline" aria-label="Processing pipeline">
    {steps.map((s, i) => (
      <li key={s.id} className={`pipeline__step is-${s.state}`} aria-current={s.state === 'active' ? 'step' : undefined}>
        <span className="pipeline__node">
          {s.state === 'done' ? <Icon name="check" strokeWidth={2.2} /> : s.state === 'warn' ? <Icon name="alert" /> : <span className="mono">{i + 1}</span>}
        </span>
        <span className="pipeline__text">
          <span className="pipeline__label">{s.label}</span>
          <span className="pipeline__detail mono">{s.detail}</span>
        </span>
      </li>
    ))}
  </ol>
)

export default Pipeline
