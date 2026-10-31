import { useEffect, useRef, useState } from 'react'
import { relativeTime } from '../../lib/format'
import { useApp } from '../../state/AppContext'
import { LogoMark } from '../brand/Logo'
import Icon from '../ui/Icon'
import ThemeToggle from '../ui/ThemeToggle'

const KIND_ICON = { ok: 'ok', info: 'info', warn: 'alert', error: 'error' }

// Closes a dropdown on an outside click or Escape.
function useDismiss(open, setOpen, ref) {
  useEffect(() => {
    if (!open) return undefined
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, setOpen, ref])
}

const initials = (name) => name.split(' ').filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('')

function AccountMenu({ user, onLogout }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const ref = useRef(null)
  useDismiss(open, setOpen, ref)

  return (
    <div className="account" ref={ref}>
      <button type="button" className="btn btn--ghost account__btn" onClick={() => setOpen((v) => !v)}
        aria-expanded={open} aria-haspopup="true" aria-label={`Account: ${user.name}`}>
        <span className="account__avatar mono" aria-hidden="true">{initials(user.name) || '?'}</span>
      </button>
      {open && (
        <div className="account__panel panel" role="dialog" aria-label="Account">
          <div className="account__who">
            <span className="account__avatar account__avatar--lg mono" aria-hidden="true">{initials(user.name) || '?'}</span>
            <div>
              <strong>{user.name}</strong>
              <span className="mono faint">{user.email}</span>
            </div>
          </div>
          <p className="account__note faint">Demo session (HttpOnly cookie). Data access is enforced again in the database by row-level security.</p>
          <div className="account__foot">
            <button type="button" className="btn btn--ghost btn--sm" disabled={busy}
              onClick={() => { setBusy(true); onLogout() }}>
              {busy ? <span className="spinner" /> : <Icon name="logout" />} Log out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

const Topbar = ({ title, eyebrow, onMenu }) => {
  const { notifications, clearNotifications, health, user, logout } = useApp()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useDismiss(open, setOpen, ref)

  return (
    <header className="topbar">
      <button type="button" className="btn btn--ghost btn--icon topbar__menu" onClick={onMenu} aria-label="Open navigation">
        <Icon name="menu" />
      </button>
      <span className="topbar__logo"><LogoMark size={28} /></span>

      <div className="topbar__title">
        <span className="label">{eyebrow}</span>
        <h1>{title}</h1>
      </div>

      <div className="topbar__right">
        <div className="case-chip is-active" title="Signed-in scope">
          <span className="label">Scope</span>
          <span className="mono case-chip__id">{user?.role === 'admin' ? 'ALL TENANTS (OPERATOR)' : `TENANT ${user?.tenant_id}`}</span>
        </div>

        <div className="topbar__engine" title={health ? 'API reachable' : 'API not reachable'}>
          <span className={`dot ${health ? 'dot--ok' : 'dot--err'}`} />
          <span className="mono">{health ? 'LIVE' : 'OFFLINE'}</span>
        </div>

        <ThemeToggle className="btn btn--ghost btn--icon theme-toggle" />

        <div className="notif" ref={ref}>
          <button
            type="button"
            className="btn btn--ghost btn--icon notif__btn"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={`Notifications (${notifications.length})`}
          >
            <Icon name="bell" />
            {notifications.length > 0 && <span className="notif__count mono">{Math.min(9, notifications.length)}</span>}
          </button>
          {open && (
            <div className="notif__panel panel" role="dialog" aria-label="Notifications">
              <div className="panel__head">
                <span className="panel__title">Notifications</span>
                <span className="label">This session</span>
              </div>
              {notifications.length === 0 ? (
                <p className="notif__empty muted">No notifications yet.</p>
              ) : (
                <ul className="notif__list">
                  {notifications.map((n) => (
                    <li key={n.id} className={`notif__item is-${n.kind}`}>
                      <Icon name={KIND_ICON[n.kind] || 'info'} />
                      <div>
                        <strong>{n.title}</strong>
                        {n.message && <p>{n.message}</p>}
                      </div>
                      <span className="mono faint">{relativeTime(n.at)}</span>
                    </li>
                  ))}
                </ul>
              )}
              {notifications.length > 0 && (
                <div className="notif__foot">
                  <button type="button" className="btn btn--ghost btn--sm" onClick={clearNotifications}>Clear</button>
                </div>
              )}
            </div>
          )}
        </div>

        {user && <AccountMenu user={user} onLogout={logout} />}
      </div>
    </header>
  )
}

export default Topbar
