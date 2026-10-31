import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { safeStorage } from '../lib/format'

const AppContext = createContext(null)

const PREFS_KEY = 'aggregatex.prefs'

export function AppProvider({ user = null, children }) {
  const [health, setHealth] = useState(null) // null = unknown / unreachable
  const [engineError, setEngineError] = useState(null)
  const [toasts, setToasts] = useState([])
  const [notifications, setNotifications] = useState([])
  const [prefs, setPrefs] = useState(() => ({ reduceMotion: false, ...safeStorage.get(PREFS_KEY, {}) }))
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

  useEffect(() => {
    const first = setTimeout(refreshHealth, 0)
    const id = setInterval(refreshHealth, 30000)
    return () => { clearTimeout(first); clearInterval(id) }
  }, [refreshHealth])

  const value = useMemo(
    () => ({
      health, engineError, refreshHealth, toasts, notify, dismissToast, notifications,
      clearNotifications: () => setNotifications([]), prefs, updatePrefs, user,
      // kept for shared shell components
      activeCase: null, providers: {},
    }),
    [health, engineError, refreshHealth, toasts, notify, dismissToast, notifications, prefs, updatePrefs, user],
  )
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useApp = () => useContext(AppContext)
