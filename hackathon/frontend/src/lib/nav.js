// Sidebar destinations (also used by the router). `admin: true` = operator only.
export const NAV = [
  { id: 'monitoring', label: 'Live Monitoring', short: 'Monitoring', icon: 'cpu', admin: true },
  { id: 'dashboard', label: 'Tenant Dashboard', short: 'Dashboard', icon: 'workspace' },
  { id: 'shards', label: 'Shards', short: 'Shards', icon: 'layers', admin: true },
  { id: 'engine', label: 'pg_trickle Engine', short: 'Engine', icon: 'cpu', admin: true },
]
