import { useApp } from '../../state/AppContext'
import { BrandLogo } from '../brand/Logo'
import Icon from '../ui/Icon'

const Sidebar = ({ current, items, open, onNavigate, onClose }) => {
  const { health, engineError, user } = useApp()
  return (
    <>
      <div className={`sidebar-scrim ${open ? 'is-open' : ''}`} onClick={onClose} aria-hidden="true" />
      <aside className={`sidebar ${open ? 'is-open' : ''}`} aria-label="Primary">
        <div className="sidebar__brand">
          <BrandLogo height={44} />
          <span className="sidebar__tag">Multi-tenant analytics · pg_trickle</span>
        </div>

        <nav className="sidebar__nav">
          <span className="label sidebar__section">Navigation</span>
          {items.map((item, i) => (
            <a
              key={item.id}
              href={`#/${item.id}`}
              className={`nav-item ${current === item.id ? 'is-active' : ''}`}
              aria-current={current === item.id ? 'page' : undefined}
              onClick={() => onNavigate?.()}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
              <span className="nav-item__key mono">{String(i + 1).padStart(2, '0')}</span>
            </a>
          ))}
        </nav>

        <div className="sidebar__status">
          <span className="label sidebar__section">System status</span>
          <div className="status-card">
            <div className="status-card__row">
              <span className={`dot ${health ? 'dot--ok dot--pulse' : 'dot--err'}`} />
              <span>{health ? 'API + database online' : 'API offline'}</span>
            </div>
            <div className="status-card__meta mono">
              {health ? `api v${health.version} · pg_trickle ${health.pg_trickle_version || '?'}` : engineError ? 'unreachable' : 'checking…'}
            </div>
          </div>
          <p className="sidebar__note">
            <Icon name="shield" />{' '}
            {user?.role === 'admin'
              ? 'Operator session: you may switch tenants. Every query still runs as the RLS-bound ax_api role.'
              : `Tenant session: the API and row-level security both restrict you to tenant ${user?.tenant_id}.`}
          </p>
        </div>
      </aside>
    </>
  )
}

export default Sidebar
