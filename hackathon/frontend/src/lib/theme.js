import { useEffect, useState } from 'react'

export const THEME_KEY = 'aggregatex.theme'
const THEME_EVENT = 'aggregatex-theme'
export const THEMES = ['dark', 'light']

export function getStoredTheme() {
  try {
    const stored = window.localStorage.getItem(THEME_KEY)
    return THEMES.includes(stored) ? stored : 'dark'
  } catch {
    return 'dark'
  }
}

let themeTimer = 0

export function applyTheme(theme) {
  const nextTheme = THEMES.includes(theme) ? theme : 'dark'
  const root = document.documentElement
  // Cross-fade colours only for a user-initiated change, never on first paint.
  if (root.dataset.theme && root.dataset.theme !== nextTheme && !root.classList.contains('reduce-motion')
    && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    root.classList.add('theme-anim')
    clearTimeout(themeTimer)
    themeTimer = setTimeout(() => root.classList.remove('theme-anim'), 400)
  }
  root.dataset.theme = nextTheme
  try {
    window.localStorage.setItem(THEME_KEY, nextTheme)
  } catch {
    // Theme remains active for the current session when storage is unavailable.
  }
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: nextTheme }))
  return nextTheme
}

// Current theme, kept in sync across every control that changes it.
export function useTheme() {
  const [theme, setTheme] = useState(getStoredTheme)
  useEffect(() => {
    const sync = (e) => setTheme(e.detail)
    window.addEventListener(THEME_EVENT, sync)
    return () => window.removeEventListener(THEME_EVENT, sync)
  }, [])
  return [theme, applyTheme]
}

export function initializeTheme() {
  document.documentElement.dataset.theme = getStoredTheme()
}
