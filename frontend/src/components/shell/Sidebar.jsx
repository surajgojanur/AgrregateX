import { witnessMode } from '../../api/witnesstrace'
import { useApp } from '../../state/AppContext'
import { BrandLogo } from '../brand/Logo'
import Icon from '../ui/Icon'
import { NAV } from '../../lib/nav'


const providerDot = (p) => (p?.available ? 'dot--ok' : p?.state === 'disabled' || p?.state === 'not_installed' ? 'dot--idle' : 'dot--warn')

const Sidebar = ({ current, open, onNavigate, onClose }) => {
  const { health, providers, engineError, wt } = useApp()
  return (
    <>
      <div className={`sidebar-scrim ${open ? 'is-open' : ''}`} onClick={onClose} aria-hidden="true" />
      <aside className={`sidebar ${open ? 'is-open' : ''}`} aria-label="Primary">
        <div className="sidebar__brand">
          <BrandLogo height={44} />
          <span className="sidebar__tag">Forensic composite workspace</span>
        </div>

        <nav className="sidebar__nav">
          <span className="label sidebar__section">Navigation</span>
          {NAV.map((item, i) => (
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
              <span>{health ? 'Local engine online' : 'Local engine offline'}</span>
            </div>
            <div className="status-card__meta mono">
              {health ? `v${health.version} · 127.0.0.1` : engineError ? 'unreachable' : 'checking…'}
            </div>
            {witnessMode ? <p className="status-card__meta mono">WitnessTrace: {wt.connection ? 'CONNECTED' : 'OFFLINE'}<br />Codex CLI: {wt.connection?.codex_installed ? 'INSTALLED' : 'UNAVAILABLE'}</p> : health && (
              <ul className="status-card__providers">
                {['offline', 'local', 'hosted'].map((id) => (
                  <li key={id} title={providers[id]?.reason}>
                    <span className={`dot ${providerDot(providers[id])}`} />
                    <span>{providers[id]?.label}</span>
                    <span className="mono faint">{providers[id]?.available ? 'READY' : (providers[id]?.state || '').replace('_', ' ').toUpperCase()}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="sidebar__note">
            <Icon name="shield" /> {witnessMode ? 'Local interface. Codex generation uses the authenticated external service; no alternative provider is used.' : 'Processing is local by default. Nothing leaves this device unless Hosted AI is configured and chosen.'}
          </p>
        </div>
      </aside>
    </>
  )
}

export default Sidebar
