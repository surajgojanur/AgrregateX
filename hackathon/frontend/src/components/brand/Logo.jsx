import { useId } from 'react'

// AggregateX brand. Inline SVG, so it scales crisply and follows the light/dark theme.
// Mark: three rising bars resting on one "sum" bar: many rows aggregated into one answer.
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
          <stop offset="0" stopColor="#22d3ee" />
          <stop offset="1" stopColor="#2563eb" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill={`url(#axg-${id})`} />
      <rect x="14" y="30" width="9" height="14" rx="3" fill="#fff" opacity="0.72" />
      <rect x="27.5" y="22" width="9" height="22" rx="3" fill="#fff" opacity="0.86" />
      <rect x="41" y="14" width="9" height="30" rx="3" fill="#fff" />
      <rect x="14" y="47" width="36" height="5" rx="2.5" fill="#fff" />
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
