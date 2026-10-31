import { useEffect, useRef, useState } from 'react'
import { BrandLogo, LogoMark } from '../components/brand/Logo'
import Icon from '../components/ui/Icon'
import ThemeToggle from '../components/ui/ThemeToggle'
import { useEngine } from './engine'
import { scrollToId, useIntroReady } from './motion'

const NAV_LINKS = [
  { id: 'platform', label: 'Platform' },
  { id: 'features', label: 'Features' },
  { id: 'how', label: 'How it works' },
  { id: 'pricing', label: 'Pricing' },
  { id: 'faq', label: 'FAQ' },
]

function EngineStatus() {
  const { status, retry } = useEngine()
  const label = status === 'online' ? 'Offline generator ready' : status === 'checking' ? 'Checking engine…' : 'Local engine not running'
  return (
    <button
      type="button"
      className={`lp-status is-${status}`}
      onClick={status === 'offline' ? retry : undefined}
      title={status === 'offline' ? 'The live demo needs a backend; none is connected yet. Click to re-check.' : 'Status of the local Revelio engine on 127.0.0.1'}
    >
      <span className="lp-status__dot" aria-hidden="true" />
      <span className="lp-status__text">{label}</span>
    </button>
  )
}

function MobileMenu({ open, onClose }) {
  const panel = useRef(null)
  const closeBtn = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    document.documentElement.classList.add('lp-locked')
    const prev = document.activeElement
    const t = setTimeout(() => closeBtn.current?.focus(), 50)
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'Tab' && panel.current) {
        const nodes = [...panel.current.querySelectorAll('a[href], button:not([disabled])')]
        const first = nodes[0]
        const last = nodes[nodes.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      clearTimeout(t)
      document.removeEventListener('keydown', onKey)
      document.documentElement.classList.remove('lp-locked')
      prev?.focus?.()
    }
  }, [open, onClose])

  return (
    <div ref={panel} className={`lp-menu ${open ? 'is-open' : ''}`} role="dialog" aria-modal="true" aria-label="Site menu" aria-hidden={!open} inert={!open}>
      <div className="lp-shell lp-menu__top">
        <span className="lp-brand">
          <LogoMark size={40} />
          <BrandLogo height={40} />
        </span>
        <button ref={closeBtn} type="button" className="lp-menu__close" onClick={onClose}>
          <Icon name="close" /> Close
        </button>
      </div>
      <nav className="lp-shell lp-menu__nav" aria-label="Sections">
        <ul>
          {NAV_LINKS.map((l, i) => (
            <li key={l.id} style={{ '--i': i }}>
              <button type="button" onClick={() => { onClose(); setTimeout(() => scrollToId(l.id), 80) }}>
                <span className="lp-mono">0{i + 1}</span>
                <span>{l.label}</span>
              </button>
            </li>
          ))}
          <li style={{ '--i': NAV_LINKS.length }}>
            <a href="/app">
              <span className="lp-mono">0{NAV_LINKS.length + 1}</span>
              <span>Open Workspace</span>
            </a>
          </li>
          <li style={{ '--i': NAV_LINKS.length + 1 }}>
            <a href="/login">
              <span className="lp-mono">0{NAV_LINKS.length + 2}</span>
              <span>Log in</span>
            </a>
          </li>
        </ul>
      </nav>
      <div className="lp-shell lp-menu__foot">
        <span>From Witness Description to Forensic Sketch.</span>
        <EngineStatus />
      </div>
    </div>
  )
}

export default function LandingNav() {
  const ready = useIntroReady()
  const [menu, setMenu] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const [active, setActive] = useState(null)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Highlight the section currently in view.
  useEffect(() => {
    if (!('IntersectionObserver' in window)) return undefined
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) setActive(e.target.id)
    }, { rootMargin: '-45% 0px -50% 0px' })
    NAV_LINKS.forEach((l) => {
      const el = document.getElementById(l.id)
      if (el) io.observe(el)
    })
    return () => io.disconnect()
  }, [])

  return (
    <>
      <header className={`lp-nav ${scrolled ? 'is-scrolled' : ''} ${ready ? 'is-ready' : ''}`}>
        <div className="lp-shell lp-nav__inner">
          <a href="/" className="lp-brand" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }) }} aria-label="Revelio — back to top">
            <LogoMark size={40} />
            <BrandLogo height={40} />
          </a>
          <nav className="lp-nav__links" aria-label="Sections">
            <ul>
              {NAV_LINKS.map((l) => (
                <li key={l.id}>
                  <a href={`#${l.id}`} aria-current={active === l.id ? 'true' : undefined}
                    onClick={(e) => { e.preventDefault(); scrollToId(l.id) }}>
                    {l.label}
                  </a>
                </li>
              ))}
              <li className="lp-nav__links-login">
                <a href="/login">Log in</a>
              </li>
            </ul>
          </nav>
          <div className="lp-nav__right">
            <EngineStatus />
            <ThemeToggle className="lp-theme-toggle" />
            <a href="/login" className="lp-nav__login">Log in</a>
            <a href="/app" className="lp-btn lp-btn--primary lp-btn--sm">
              Open Workspace <Icon name="arrowRight" />
            </a>
            <button type="button" className="lp-nav__menu" onClick={() => setMenu(true)} aria-haspopup="dialog" aria-expanded={menu} aria-label="Open menu">
              <Icon name="menu" />
            </button>
          </div>
        </div>
      </header>
      <MobileMenu open={menu} onClose={() => setMenu(false)} />
    </>
  )
}
