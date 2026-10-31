import Icon from '../ui/Icon'

const KIND = {
  default: { icon: 'info', cls: 'is-default', label: 'Neutral default' },
  unspecified: { icon: 'info', cls: 'is-default', label: 'Unspecified' },
  conflict: { icon: 'alert', cls: 'is-warn', label: 'Conflict' },
  limitation: { icon: 'alert', cls: 'is-warn', label: 'Limitation' },
  not_rendered: { icon: 'eyeOff', cls: 'is-muted', label: 'Recorded only' },
  tone: { icon: 'eye', cls: 'is-muted', label: 'Tone only' },
  ai: { icon: 'alert', cls: 'is-warn', label: 'AI output' },
}

// Honest renderer report: what was drawn from defaults, what is not drawn at all.
const RenderNotes = ({ notes = [] }) => {
  if (!notes.length) return null
  const order = ['conflict', 'limitation', 'ai', 'unspecified', 'default', 'tone', 'not_rendered']
  const sorted = [...notes].sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind))
  return (
    <section className="panel notes" aria-labelledby="notes-title">
      <div className="panel__head">
        <h2 id="notes-title" className="panel__title section-title">Renderer report</h2>
        <span className="mono faint">{notes.length} note{notes.length > 1 ? 's' : ''}</span>
      </div>
      <ul className="notes__list">
        {sorted.map((n, i) => {
          const k = KIND[n.kind] || KIND.default
          return (
            <li key={`${n.trait}-${i}`} className={`note ${k.cls}`}>
              <Icon name={k.icon} />
              <span className="tag">{k.label}</span>
              <span>{n.message}</span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

export default RenderNotes
