import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { initializeTheme } from './lib/theme'

/* eslint-disable react-refresh/only-export-components -- entry file, not a component module */

// Entry points, one Vite build:
//   /                   -> landing page (the problem and how AggregateX answers it)
//   /login              -> demo sign-in (skipped by the API when login is disabled)
//   /app                -> tenant analytics dashboard (#/dashboard, #/shards, #/engine)
const App = lazy(() => import('./App.jsx'))
const LandingPage = lazy(() => import('./landing/LandingPage.jsx'))
const AuthPage = lazy(() => import('./auth/AuthPage.jsx'))

initializeTheme()

const { pathname } = window.location
const isApp = pathname === '/app' || pathname.startsWith('/app/')
const isAuth = ['/login', '/register'].includes(pathname.replace(/\/$/, ''))
document.title = isApp ? 'AggregateX — Tenant Analytics' : isAuth ? 'Sign in — AggregateX' : 'AggregateX — Multi-tenant analytics'

let page = <LandingPage />
if (isApp) page = <App />
else if (isAuth) page = <AuthPage />

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Suspense fallback={null}>{page}</Suspense>
  </StrictMode>,
)
