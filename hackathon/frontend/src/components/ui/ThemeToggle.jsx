import Icon from './Icon'
import { useTheme } from '../../lib/theme'

export default function ThemeToggle({ className = '' }) {
  const [theme, setTheme] = useTheme()
  const nextTheme = theme === 'dark' ? 'light' : 'dark'
  const label = `Switch to ${nextTheme} theme`

  return (
    <button
      type="button"
      className={className}
      onClick={() => setTheme(nextTheme)}
      aria-label={label}
      title={label}
    >
      <span key={theme} className="theme-toggle__icon"><Icon name={theme === 'dark' ? 'sun' : 'moon'} /></span>
    </button>
  )
}
