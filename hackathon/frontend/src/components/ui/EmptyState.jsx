import Icon from './Icon'

// Lightweight line illustrations; strokes follow currentColor so both themes work.
const ART = {
  reticle: (
    <>
      <circle className="empty-art__ring" cx="40" cy="40" r="26" />
      <circle cx="40" cy="40" r="15" />
      <path d="M40 6v12M40 62v12M6 40h12M62 40h12" />
      <circle className="empty-art__dot" cx="40" cy="40" r="2.5" />
    </>
  ),
  timeline: (
    <>
      <path d="M14 40h52" strokeDasharray="3 4" />
      <circle cx="18" cy="40" r="5" />
      <circle className="empty-art__dot" cx="40" cy="40" r="5" />
      <circle cx="62" cy="40" r="5" strokeDasharray="2 3" />
      <path d="M40 30v-8M32 22h16" />
    </>
  ),
  document: (
    <>
      <path d="M24 12h22l12 12v44H24z" />
      <path d="M46 12v12h12" />
      <path className="empty-art__line" d="M31 36h20M31 44h20M31 52h12" />
    </>
  ),
  search: (
    <>
      <circle className="empty-art__ring" cx="35" cy="35" r="17" />
      <path d="M47.5 47.5 62 62" />
      <path d="M28 35h14" strokeDasharray="2 3" />
    </>
  ),
  connection: (
    <>
      <rect x="10" y="30" width="18" height="20" rx="3" />
      <rect x="52" y="30" width="18" height="20" rx="3" />
      <path d="M28 40h8M44 40h8" />
      <path className="empty-art__break" d="M37 35l6 10M43 35l-6 10" />
    </>
  ),
  compare: (
    <>
      <rect x="12" y="16" width="24" height="48" rx="3" />
      <rect x="44" y="16" width="24" height="48" rx="3" strokeDasharray="3 3" />
      <path className="empty-art__line" d="M40 10v60" />
    </>
  ),
}

const EmptyState = ({ icon = 'scan', art, title, children, action, compact = false }) => (
  <div className={`empty ${compact ? 'empty--compact' : ''}`}>
    {art === 'none' ? null : ART[art] ? (
      <svg className={`empty-art empty-art--${art}`} viewBox="0 0 80 80" aria-hidden="true" focusable="false">{ART[art]}</svg>
    ) : (
      <div className="empty__icon" aria-hidden="true">
        <span className="empty__ring" />
        <Icon name={icon} />
      </div>
    )}
    <h3 className="empty__title">{title}</h3>
    {children && <div className="empty__text">{children}</div>}
    {action && <div className="empty__action">{action}</div>}
  </div>
)

export default EmptyState
