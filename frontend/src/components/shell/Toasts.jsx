import { useApp } from '../../state/AppContext'
import Icon from '../ui/Icon'

const ICON = { ok: 'ok', info: 'info', warn: 'alert', error: 'error' }

const Toasts = () => {
  const { toasts, dismissToast } = useApp()
  return (
    <div className="toasts" aria-live="polite" aria-relevant="additions">
      {toasts.map((t) => (
        <div key={t.id} className={`toast is-${t.kind}`} role={t.kind === 'error' ? 'alert' : 'status'}>
          <Icon name={ICON[t.kind] || 'info'} />
          <div className="toast__body">
            <strong>{t.title}</strong>
            {t.message && <p>{t.message}</p>}
          </div>
          <button type="button" className="btn btn--ghost btn--icon btn--sm" onClick={() => dismissToast(t.id)} aria-label="Dismiss">
            <Icon name="close" />
          </button>
        </div>
      ))}
    </div>
  )
}

export default Toasts
