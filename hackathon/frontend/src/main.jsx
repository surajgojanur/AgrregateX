import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { initializeTheme } from './lib/theme'

/* eslint-disable react-refresh/only-export-components -- entry file, not a component module */

// Entry points, one Vite build:
//   /                   → marketing landing page
//   /login, /register   → local account pages
//   /app                → the Revelio workspace (requires a login; uses #/hash routes internally)
const App = lazy(() => import('./App.jsx'))
const LandingPage = lazy(() => import('./landing/LandingPage.jsx'))
const AuthPage = lazy(() => import('./auth/AuthPage.jsx'))

// One-time carry-over of browser storage saved before the project was renamed.
try {
  for (const k of ['draft', 'prefs']) {
    const old = window.localStorage.getItem(`verisketch.${k}`)
    if (old != null && window.localStorage.getItem(`revelio.${k}`) == null) window.localStorage.setItem(`revelio.${k}`, old)
  }
} catch {
  /* storage unavailable */
}

initializeTheme()

const { pathname, hash, search } = window.location

// Old bookmarks such as /#/library belonged to the workspace: keep them working.
if ((pathname === '/' || pathname === '') && hash.startsWith('#/')) {
  window.location.replace(`/app${search}${hash}`)
}

const isApp = pathname === '/app' || pathname.startsWith('/app/')
const authMode = { '/login': 'login', '/register': 'register' }[pathname.replace(/\/$/, '')]
document.title = isApp ? 'Revelio — Forensic Composite Workspace' : 'Revelio — From Witness Description to Forensic Sketch'

let page = <LandingPage />
if (isApp) page = <App />
else if (authMode) page = <AuthPage mode={authMode} />

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Suspense fallback={null}>{page}</Suspense>
  </StrictMode>,
)
