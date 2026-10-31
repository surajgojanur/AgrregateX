import { useId } from 'react'

// AggregateX brand: an architectural AX monogram made from layered data rails.
export const LogoMark = ({ size = 32, animated = false, title }) => {
  const id = useId().replace(/:/g, '')
  return (
    <svg
      className={`logo-mark ${animated ? 'is-animated' : ''}`}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : 'true'}
      aria-label={title}
      focusable="false"
    >
      <defs>
        <linearGradient id={`axg-${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" className="logo-gradient__start" />
          <stop offset="1" className="logo-gradient__end" />
        </linearGradient>
        <filter id={`axs-${id}`} x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="4" stdDeviation="4" floodColor="#07111f" floodOpacity="0.28" />
        </filter>
      </defs>
      <rect width="64" height="64" rx="17" fill={`url(#axg-${id})`} />
      <path d="M14 16.5 31.5 34 14 51.5" fill="none" stroke="#fff" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" filter={`url(#axs-${id})`} />
      <path d="M50 16.5 32.5 34 50 51.5" fill="none" stroke="#fff" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" opacity="0.96" />
      <circle cx="32" cy="34" r="4.5" fill="#11264a" stroke="#dffaff" strokeWidth="2" />
    </svg>
  )
}

// Full logo: mark + "AggregateX" wordmark (live text in the app font, theme-aware colour).
// `height` matches the old <img> API. Pass mark={false} for the wordmark alone.
export const BrandLogo = ({ height = 32, animated = false, className = '', mark = true }) => (
  <span
    className={`brand-logo ${animated ? 'is-animated' : ''} ${className}`}
    style={{ height, gap: Math.round(height * 0.28), fontSize: Math.round(height * 0.56) }}
    role="img"
    aria-label="AggregateX"
  >
    {mark && <LogoMark size={height} />}
    <span className="brand-logo__text" aria-hidden="true">
      Aggregate<span className="brand-logo__x">X</span>
    </span>
  </span>
)

export const Wordmark = ({ compact = false }) => (
  <span className="wordmark">
    <span className="wordmark__name">
      Aggregate<span className="wordmark__ai">X</span>
    </span>
    {!compact && <span className="wordmark__tag">Multi-tenant analytics</span>}
  </span>
)
