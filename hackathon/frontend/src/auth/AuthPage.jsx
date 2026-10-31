import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { NO_BACKEND, previewMode } from '../services/previewBackend'
import { BrandLogo, LogoMark } from '../components/brand/Logo'
import Icon from '../components/ui/Icon'
import ThemeToggle from '../components/ui/ThemeToggle'
import { safeNext } from '../lib/auth'
import '../landing/landing.css'
import './auth.css'

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

function validate(mode, f) {
  const errors = {}
  if (mode === 'register' && !f.name.trim()) errors.name = 'Enter your name.'
  if (!EMAIL_RE.test(f.email.trim())) errors.email = 'Enter a valid email address.'
  if (mode === 'register') {
    if (f.password.length < 8) errors.password = 'Use at least 8 characters.'
    else if (f.password.length > 128) errors.password = 'Use at most 128 characters.'
    if (f.confirm !== f.password) errors.confirm = 'Passwords do not match.'
  } else if (!f.password) {
    errors.password = 'Enter your password.'
  }
  return errors
}

function Field({ id, label, error, hint, children }) {
  return (
    <div className={`lp-auth__field ${error ? 'has-error' : ''}`}>
      <label htmlFor={id} className="lp-label">{label}</label>
      {children}
      {error ? <p id={`${id}-err`} className="lp-error">{error}</p> : hint ? <p id={`${id}-hint`} className="lp-faint lp-auth__hint">{hint}</p> : null}
    </div>
  )
}

export default function AuthPage({ mode }) {
  const isRegister = mode === 'register'
  const next = safeNext(new URLSearchParams(window.location.search).get('next'))
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' })
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [show, setShow] = useState(false)
  const [engine, setEngine] = useState(previewMode ? 'offline' : 'checking') // checking | online | offline
  const first = useRef(null)

  useEffect(() => {
    document.title = `${isRegister ? 'Create account' : 'Log in'} — Revelio`
    first.current?.focus()
    // Already logged in: go straight to the workspace.
    // Preview mode has a placeholder session only: stay on this page instead of redirecting.
    if (previewMode) return
    api.me()
      .then(() => window.location.replace(next))
      .catch((err) => setEngine(err.isOffline ? 'offline' : 'online'))
  }, [isRegister, next])

  const set = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }))
    if (errors[key]) setErrors((x) => ({ ...x, [key]: undefined }))
    setServerError(null)
  }

  const submit = async (e) => {
    e.preventDefault()
    const found = validate(mode, form)
    setErrors(found)
    if (Object.keys(found).length) {
      document.getElementById(`auth-${Object.keys(found)[0]}`)?.focus()
      return
    }
    setBusy(true)
    setServerError(null)
    try {
      if (isRegister) await api.register(form.name.trim(), form.email.trim(), form.password)
      else await api.login(form.email.trim(), form.password)
      window.location.assign(next)
    } catch (err) {
      setServerError(err.isOffline ? 'The backend is not reachable. Try again once it is running.' : err.message)
      if (err.isOffline) setEngine('offline')
      setBusy(false)
    }
  }

  const other = `${isRegister ? '/login' : '/register'}${next !== '/app' ? `?next=${encodeURIComponent(next)}` : ''}`
  const describedBy = (k) => (errors[k] ? `auth-${k}-err` : undefined)

  return (
    <div className="lp lp-auth">
      <header className="lp-auth__top">
        <a href="/" className="lp-brand" aria-label="Revelio home">
          <LogoMark size={36} />
          <BrandLogo height={36} />
        </a>
        <ThemeToggle className="lp-theme-toggle" />
      </header>

      <main className="lp-auth__main">
        <aside className="lp-auth__side" aria-hidden="true">
          <div className="lp-auth__frame">
            <img src="/landing/demo-r2.webp" alt="" />
            <span className="lp-tag lp-tag--ai">AI sketch · fictional</span>
          </div>
          <p className="lp-eyebrow">Forensic composite workspace</p>
          <p className="lp-auth__quote">From witness description to forensic sketch.</p>
        </aside>

        <section className="lp-auth__card" aria-labelledby="auth-title">
          <span className="lp-eyebrow">{isRegister ? 'New account' : 'Welcome back'}</span>
          <h1 id="auth-title">{isRegister ? 'Create your account' : 'Log in to Revelio'}</h1>
          <p className="lp-auth__lead">
            {isRegister
              ? 'Your account is stored only in the Revelio database on this machine. Nothing is sent to an external server.'
              : 'Log in to open the investigation workspace and your saved sketches.'}
          </p>

          {engine === 'offline' && (
            <p className="lp-auth__notice" role="status">
              <Icon name="cpu" /> <span>{previewMode ? <>{NO_BACKEND} <a href="/app">Browse the workspace in preview mode</a>.</> : 'The backend isn’t running, so accounts can’t be checked.'}</span>
            </p>
          )}

          <form className="lp-auth__form" onSubmit={submit} noValidate>
            {isRegister && (
              <Field id="auth-name" label="Full name" error={errors.name}>
                <input ref={first} id="auth-name" className="lp-input" autoComplete="name" maxLength={80}
                  value={form.name} onChange={set('name')} aria-invalid={Boolean(errors.name)} aria-describedby={describedBy('name')} />
              </Field>
            )}
            <Field id="auth-email" label="Email" error={errors.email}>
              <input ref={isRegister ? undefined : first} id="auth-email" className="lp-input" type="email" autoComplete="email"
                inputMode="email" maxLength={254} value={form.email} onChange={set('email')}
                aria-invalid={Boolean(errors.email)} aria-describedby={describedBy('email')} />
            </Field>
            <Field id="auth-password" label="Password" error={errors.password} hint={isRegister ? 'At least 8 characters.' : null}>
              <div className="lp-auth__pw">
                <input id="auth-password" className="lp-input" type={show ? 'text' : 'password'}
                  autoComplete={isRegister ? 'new-password' : 'current-password'} maxLength={128}
                  value={form.password} onChange={set('password')} aria-invalid={Boolean(errors.password)}
                  aria-describedby={errors.password ? 'auth-password-err' : isRegister ? 'auth-password-hint' : undefined} />
                <button type="button" className="lp-auth__eye" onClick={() => setShow((v) => !v)}
                  aria-label={show ? 'Hide password' : 'Show password'} aria-pressed={show}>
                  <Icon name={show ? 'eyeOff' : 'eye'} />
                </button>
              </div>
            </Field>
            {isRegister && (
              <Field id="auth-confirm" label="Confirm password" error={errors.confirm}>
                <input id="auth-confirm" className="lp-input" type={show ? 'text' : 'password'} autoComplete="new-password"
                  maxLength={128} value={form.confirm} onChange={set('confirm')}
                  aria-invalid={Boolean(errors.confirm)} aria-describedby={describedBy('confirm')} />
              </Field>
            )}

            {serverError && <p className="lp-error lp-auth__server" role="alert">{serverError}</p>}

            <button type="submit" className="lp-btn lp-btn--primary lp-btn--block lp-btn--lg" disabled={busy}>
              {busy ? <span className="lp-spinner" /> : <Icon name={isRegister ? 'user' : 'lock'} />}
              {isRegister ? 'Create account' : 'Log in'}
            </button>
          </form>

          <p className="lp-auth__switch">
            {isRegister ? 'Already have an account?' : 'New to Revelio?'} <a href={other}>{isRegister ? 'Log in' : 'Create an account'}</a>
          </p>
          {isRegister && (
            <p className="lp-faint lp-auth__fine">
              Every account on this machine shares the same local sketch library. There is no password-reset email, so keep your password somewhere safe.
            </p>
          )}
        </section>
      </main>
    </div>
  )
}
