import { lazy, Suspense, useEffect, useState } from 'react'
import { api } from './api/client'
import Sidebar from './components/shell/Sidebar'
import Toasts from './components/shell/Toasts'
import Topbar from './components/shell/Topbar'
import { loginUrl } from './lib/auth'
import { NAV } from './lib/nav'
import { useRoute } from './lib/router'
import { AppProvider } from './state/AppContext'
import './styles/app.css'
import './styles/motion.css'
import './pages/dashboard.css'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Engine = lazy(() => import('./pages/Engine'))

const TITLES = {
  dashboard: ['Tenant analytics', 'Dashboard'],
  engine: ['pg_trickle internals', 'Engine'],
}

function PageFallback() {
  return (
    <div className="page-fallback" aria-busy="true">
      <div className="skeleton" style={{ height: 28, width: 260 }} />
      <div className="skeleton" style={{ height: 220 }} />
    </div>
  )
}

function Shell({ user }) {
  const route = useRoute()
  const [navOpen, setNavOpen] = useState(false)
  const allowed = NAV.filter((n) => !n.admin || user.role === 'admin')
  const page = allowed.some((n) => n.id === route.path) ? route.path : 'dashboard'
  const [eyebrow, title] = TITLES[page]

  return (
    <div className="app">
      <a href="#main" className="skip-link">Skip to content</a>
      <Sidebar current={page} items={allowed} open={navOpen} onNavigate={() => setNavOpen(false)} onClose={() => setNavOpen(false)} />
      <div className="app__main">
        <Topbar title={title} eyebrow={eyebrow} onMenu={() => setNavOpen(true)} />
        <main id="main" className="content" key={page}>
          <Suspense fallback={<PageFallback />}>
            {page === 'engine' ? <Engine /> : <Dashboard params={route.params} />}
          </Suspense>
        </main>
        <footer className="app__foot">
          <span className="mono">AGRREGATEX · powered by pg_trickle (Apache-2.0, trickle-labs)</span>
          <span>Representative demo data · not organizer data.</span>
        </footer>
      </div>
      <Toasts />
    </div>
  )
}

export default function App() {
  const [auth, setAuth] = useState({ checked: false, user: null })

  useEffect(() => {
    api.me()
      .then((r) => setAuth({ checked: true, user: r.user }))
      .catch((err) => {
        if (err.status === 401) window.location.replace(loginUrl())
        else setAuth({ checked: true, user: null, error: err.message })
      })
  }, [])

  if (!auth.checked) return null
  if (!auth.user) {
    return (
      <div className="engine-offline panel" role="alert">
        <h2>API unavailable</h2>
        <p>{auth.error}</p>
        <button className="btn" onClick={() => window.location.reload()}>Retry</button>
      </div>
    )
  }
  return (
    <AppProvider user={auth.user}>
      <Shell user={auth.user} />
    </AppProvider>
  )
}
