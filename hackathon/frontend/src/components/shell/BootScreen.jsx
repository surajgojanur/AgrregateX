import { BrandLogo } from '../brand/Logo'
import Icon from '../ui/Icon'

const STEP_LABELS = {
  ui: 'Interface loaded',
  engine: 'Local engine (127.0.0.1)',
  catalog: 'Facial-trait catalog',
  providers: 'Generation providers',
}

const statusIcon = (s) => {
  if (s === 'ok') return <Icon name="check" className="icon boot__ok" />
  if (s === 'error') return <Icon name="close" className="icon boot__err" />
  if (s === 'skipped') return <span className="boot__skip">—</span>
  return <span className="spinner boot__spin" aria-hidden="true" />
}

// Short boot sequence. Every line reflects a real check performed by App.
const BootScreen = ({ steps, leaving }) => {
  const done = Object.values(steps).filter((s) => s !== 'pending').length
  const pct = Math.round((done / Object.keys(steps).length) * 100)
  return (
    <div className={`boot ${leaving ? 'is-leaving' : ''}`} role="status" aria-live="polite">
      <div className="boot__grid" aria-hidden="true" />
      <div className="boot__card">
        <div className="boot__brand">
          <BrandLogo height={72} animated />
          <span className="boot__tag">From Witness Description to Forensic Sketch.</span>
        </div>
        <div className="boot__status label label--cyan">Initializing forensic workspace</div>
        <div className="boot__bar" aria-hidden="true">
          <span style={{ transform: `scaleX(${pct / 100})` }} />
        </div>
        <ul className="boot__steps">
          {Object.entries(steps).map(([key, s]) => (
            <li key={key} className={`boot__step is-${s}`}>
              {statusIcon(s)}
              <span>{STEP_LABELS[key]}</span>
              <span className="mono boot__state">{s === 'pending' ? '…' : s.toUpperCase()}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export default BootScreen
