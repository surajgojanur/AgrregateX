import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { witnessMode } from '../api/witnesstrace'
import useWitnessCases from './useWitnessCases'
import { safeStorage } from '../lib/format'

const AppContext = createContext(null)

const PREFS_KEY = 'revelio.prefs'

export function AppProvider({ user = null, children }) {
  const wt = useWitnessCases()
  const [catalog, setCatalog] = useState(null)
  const [health, setHealth] = useState(null) // null = unknown yet
  const [engineError, setEngineError] = useState(null)
  const [toasts, setToasts] = useState([])
  const [notifications, setNotifications] = useState([])
  const [activeCase, setActiveCase] = useState(null) // { id, title, revision } | { draft: true }
  const [prefs, setPrefs] = useState(() => ({ scanEffect: true, reduceMotion: false, ...safeStorage.get(PREFS_KEY, {}) }))
  const toastId = useRef(0)

  const refreshHealth = useCallback(async () => {
    try {
      const h = await api.health()
      setHealth(h)
      setEngineError(null)
      return h
    } catch (err) {
      setHealth(null)
      setEngineError(err.message)
      return null
    }
  }, [])

  const loadCatalog = useCallback(async () => {
    const c = await api.catalog()
    setCatalog(c)
    return c
  }, [])

  // Ends the session and drops this browser's unsaved draft, so the next person at this machine can't read it.
  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      /* the session cookie is cleared server-side when reachable; leave either way */
    }
    safeStorage.remove('revelio.draft')
    window.location.assign('/login')
  }, [])

  const dismissToast = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), [])

  const notify = useCallback(
    ({ kind = 'info', title, message, timeout = 4200 }) => {
      toastId.current += 1
      const id = toastId.current
      const entry = { id, kind, title, message, at: new Date().toISOString() }
      setToasts((t) => [...t.slice(-3), entry])
      setNotifications((n) => [entry, ...n].slice(0, 30))
      if (timeout) setTimeout(() => dismissToast(id), timeout)
      return id
    },
    [dismissToast],
  )

  const updatePrefs = useCallback((patch) => {
    setPrefs((p) => {
      const next = { ...p, ...patch }
      safeStorage.set(PREFS_KEY, next)
      return next
    })
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle('reduce-motion', Boolean(prefs.reduceMotion))
  }, [prefs.reduceMotion])

  // Re-check engine status every 30 s (cheap local call).
  useEffect(() => {
    const id = setInterval(refreshHealth, 30000)
    return () => clearInterval(id)
  }, [refreshHealth])

  const providers = useMemo(() => {
    const map = {}
    for (const p of health?.providers || []) map[p.id] = p
    return map
  }, [health])

  const value = useMemo(
    () => ({
      wt, catalog, loadCatalog, health, providers, engineError, refreshHealth,
      toasts, notify, dismissToast, notifications, clearNotifications: () => setNotifications([]),
      activeCase: witnessMode ? wt.record : activeCase, setActiveCase, prefs, updatePrefs, user, logout,
    }),
    [wt, user, logout, catalog, loadCatalog, health, providers, engineError, refreshHealth, toasts, notify, dismissToast,
      notifications, activeCase, prefs, updatePrefs],
  )
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useApp = () => useContext(AppContext)
