import logoMark from '../../assets/brand/logo-mark.png'
import logoFull from '../../assets/brand/logo-wordmark.png'

// Brand mark: the owl from the supplied logo (src/images/image-removebg-preview.png),
// cropped to a square transparent icon. One component, used everywhere.
export const LogoMark = ({ size = 32, animated = false }) => (
  <img
    className={`logo-mark ${animated ? 'is-animated' : ''}`}
    src={logoMark}
    width={size}
    height={size}
    alt=""
    aria-hidden="true"
    draggable={false}
    decoding="async"
  />
)

// Full logo (src/images/image-removebg-preview.png, cleaned). Replaces the text name.
const LOGO_RATIO = 554 / 170
export const BrandLogo = ({ height = 32, animated = false, className = '' }) => (
  <img
    className={`brand-logo ${animated ? 'is-animated' : ''} ${className}`}
    src={logoFull}
    height={height}
    width={Math.round(height * LOGO_RATIO)}
    alt="Revelio"
    draggable={false}
    decoding="async"
  />
)

export const Wordmark = ({ compact = false }) => (
  <span className="wordmark">
    <span className="wordmark__name">
      Revelio
    </span>
    {!compact && <span className="wordmark__tag">Forensic composite workspace</span>}
  </span>
)
