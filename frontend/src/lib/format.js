export const humanize = (v) => (v == null ? 'Unknown' : String(v).replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase()))

export const optionLabel = (trait, value) => {
  if (value == null) return 'Unknown'
  return trait?.option_labels?.[value] || humanize(value)
}

const pad = (n) => String(n).padStart(2, '0')

export const formatDateTime = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export const relativeTime = (iso, now = Date.now()) => {
  if (!iso) return ''
  const diff = Math.round((now - new Date(iso).getTime()) / 1000)
  if (diff < 45) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`
  if (diff < 86400 * 7) return `${Math.round(diff / 86400)} d ago`
  return formatDateTime(iso).split(' ')[0]
}

export const markLabel = (m) =>
  `${humanize(m.size)} ${m.type} · ${String(m.location).replace(/_/g, ' ')}${m.side_specified === false ? ' (side not stated)' : ''}`

/** Count of traits with a value, conflicts, and unknowns in a profile. */
export const profileSummary = (profile, catalog) => {
  const traits = profile?.traits || {}
  let known = 0
  let conflicts = 0
  let unknown = 0
  for (const t of catalog?.traits || []) {
    const tv = traits[t.key]
    if (tv?.value) known += 1
    else if (tv?.alternatives?.length) conflicts += 1
    else unknown += 1
  }
  return { known, conflicts, unknown, marks: profile?.marks?.length || 0 }
}

export const emptyProfile = () => ({ traits: {}, marks: [], adjustments: {}, observations: '' })

export const downloadBlob = (blob, filename) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const safeStorage = {
  get(key, fallback = null) {
    try {
      const raw = window.localStorage.getItem(key)
      return raw == null ? fallback : JSON.parse(raw)
    } catch {
      return fallback
    }
  },
  set(key, value) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value))
    } catch {
      /* storage unavailable */
    }
  },
  remove(key) {
    try {
      window.localStorage.removeItem(key)
    } catch {
      /* storage unavailable */
    }
  },
}
