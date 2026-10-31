import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from '../api/client'

/* eslint-disable react-refresh/only-export-components */

// Real status of the local Revelio engine — never a decorative "live" badge.
const EngineContext = createContext(null)

export function EngineProvider({ children }) {
  const [state, setState] = useState({ status: 'checking', health: null, catalog: null, error: null })

  const check = useCallback(async () => {
    setState((s) => ({ ...s, status: 'checking', error: null }))
    try {
      const [health, catalog] = await Promise.all([api.health(), api.catalog()])
      setState({ status: 'online', health, catalog, error: null })
    } catch (err) {
      setState({ status: 'offline', health: null, catalog: null, error: err.message })
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    Promise.all([api.health(), api.catalog()])
      .then(([health, catalog]) => !cancelled && setState({ status: 'online', health, catalog, error: null }))
      .catch((err) => !cancelled && setState({ status: 'offline', health: null, catalog: null, error: err.message }))
    return () => {
      cancelled = true
    }
  }, [])

  return <EngineContext.Provider value={{ ...state, retry: check }}>{children}</EngineContext.Provider>
}

export const useEngine = () => useContext(EngineContext)
