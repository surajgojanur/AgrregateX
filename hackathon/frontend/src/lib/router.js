import { useEffect, useState } from 'react'

// Minimal hash router: #/route?key=value. Survives reloads, no dependency.
const parse = () => {
  const raw = window.location.hash.replace(/^#\/?/, '')
  const [path, query = ''] = raw.split('?')
  return { path: path || 'workspace', params: Object.fromEntries(new URLSearchParams(query)) }
}

export const navigate = (path, params = {}) => {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== '')).toString()
  const next = `#/${path}${qs ? `?${qs}` : ''}`
  if (window.location.hash !== next) window.location.hash = next
}

export const useRoute = () => {
  const [route, setRoute] = useState(parse)
  useEffect(() => {
    const onHash = () => setRoute(parse())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  return route
}
