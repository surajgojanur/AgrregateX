import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { initializeTheme } from './lib/theme'

/* eslint-disable react-refresh/only-export-components -- entry file, not a component module */

// Entry points, one Vite build:
//   /                   -> landing page (the problem and how AggregateX answers it)
//   /login, /register   -> landing redirect
//   /app                -> tenant analytics dashboard (#/dashboard, #/shards, #/engine)
const App = lazy(() => import('./App.jsx'))
const LandingPage = lazy(() => import('./landing/LandingPage.jsx'))


initializeTheme()

const { pathname } = window.location
const isApp = pathname === '/app' || pathname.startsWith('/app/')
const isAuth = ['/login', '/register'].includes(pathname.replace(/\/$/, ''))
if (isAuth) window.location.replace('/')
document.title = isApp ? 'AggregateX — Tenant Analytics' : 'AggregateX — Multi-tenant analytics'

let page = <LandingPage />
if (isApp) page = <App />


createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Suspense fallback={null}>{page}</Suspense>
  </StrictMode>,
)
