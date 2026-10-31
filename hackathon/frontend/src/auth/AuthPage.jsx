import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { BrandLogo } from '../components/brand/Logo'
import ThemeToggle from '../components/ui/ThemeToggle'
import { safeNext } from '../lib/auth'
import './auth.css'

// Demo sign-in. Accounts: tenant<N>@demo.local (one tenant) and admin@demo.local (operator).
// When the API runs with login disabled, /api/auth/me succeeds and we go straight to the dashboard.
export default function AuthPage() {
  const next = safeNext(new URLSearchParams(window.location.search).get('next'))
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [api503, setApi503] = useState(false)
  const first = useRef(null)

  useEffect(() => {
    first.current?.focus()
    api.me()
      .then(() => window.location.replace(next))
      .catch((err) => setApi503(err.isOffline))
  }, [next])

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!email.trim() || !password) {
      setError('Enter your email and password.')
      return
    }
    setBusy(true)
    try {
      await api.login(email.trim(), password)
      window.location.replace(next)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <main className="ax-auth">
      <div className="ax-auth__top">
        <a href="/" aria-label="AggregateX home"><BrandLogo height={34} /></a>
        <ThemeToggle className="btn btn--ghost btn--icon" />
      </div>
      <form className="ax-auth__card panel" onSubmit={submit} noValidate>
        <h1>Sign in</h1>
        <p className="muted">Tenant dashboards for the multi-tenant aggregation layer.</p>
        {api503 && <p className="alert" role="alert">The AggregateX API is not reachable. Start the stack, then retry.</p>}
        <label className="ax-auth__field">
          <span className="label">Email</span>
          <input ref={first} className="input" type="email" autoComplete="username" value={email}
            onChange={(e) => setEmail(e.target.value)} placeholder="tenant2@demo.local" />
        </label>
        <label className="ax-auth__field">
          <span className="label">Password</span>
          <input className="input" type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p className="ax-auth__error" role="alert">{error}</p>}
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? <span className="spinner" /> : null} Sign in
        </button>
        <p className="faint ax-auth__hint">
          Demo accounts: <span className="mono">tenant1@demo.local</span> … <span className="mono">tenant10@demo.local</span> see one
          tenant; <span className="mono">admin@demo.local</span> is the operator. Self-registration is disabled.
        </p>
      </form>
    </main>
  )
}
