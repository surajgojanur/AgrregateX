import { createContext, useContext, useEffect, useRef, useState } from 'react'

/* eslint-disable react-refresh/only-export-components */

export const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

export const canHover = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(hover: hover) and (pointer: fine)').matches

const INTRO_SEEN_KEY = 'revelio.intro.seen'

/** True when the intro should be skipped (already seen this session, or reduced motion). */
export const shouldSkipIntro = () => {
  if (prefersReducedMotion()) return true
  try {
    return window.sessionStorage.getItem(INTRO_SEEN_KEY) === '1'
  } catch {
    return false
  }
}

export const markIntroSeen = () => {
  try {
    window.sessionStorage.setItem(INTRO_SEEN_KEY, '1')
  } catch {
    /* storage unavailable */
  }
}

/** Intro gate: hero reveals wait until the intro has left the screen. */
export const IntroContext = createContext(true)
export const useIntroReady = () => useContext(IntroContext)

/** true once the element has entered the viewport (never flips back). */
export function useInView(ref, { rootMargin = '0px 0px -12% 0px', threshold = 0.15 } = {}) {
  const [inView, setInView] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || inView) return undefined
    if (!('IntersectionObserver' in window)) {
      const id = requestAnimationFrame(() => setInView(true))
      return () => cancelAnimationFrame(id)
    }
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setInView(true)
        io.disconnect()
      }
    }, { rootMargin, threshold })
    io.observe(el)
    return () => io.disconnect()
  }, [ref, inView, rootMargin, threshold])
  return inView
}

/** Fade/slide in when scrolled into view. `gate` delays the reveal (intro). */
export function Reveal({ as = 'div', delay = 0, y = 24, scale, gate = true, className = '', style, children, ...rest }) {
  const Tag = as
  const ref = useRef(null)
  const inView = useInView(ref)
  const on = inView && gate
  return (
    <Tag
      ref={ref}
      className={`lp-reveal ${on ? 'is-in' : ''} ${className}`}
      style={{ '--d': `${delay}ms`, '--y': `${y}px`, '--s': scale ?? 1, ...style }}
      {...rest}
    >
      {children}
    </Tag>
  )
}

/** Masked line reveal: each line slides up from behind a clip, staggered. */
export function SplitLines({ lines, as = 'h2', className = '', delay = 0, stagger = 110, gate = true }) {
  const Tag = as
  const ref = useRef(null)
  const inView = useInView(ref)
  const on = inView && gate
  return (
    <Tag ref={ref} className={`lp-lines ${on ? 'is-in' : ''} ${className}`} aria-label={lines.join(' ')}>
      {lines.map((line, i) => (
        <span className="lp-lines__mask" aria-hidden="true" key={i}>
          <span className="lp-lines__line" style={{ '--d': `${delay + i * stagger}ms` }}>{line}</span>
        </span>
      ))}
    </Tag>
  )
}

/** Word-by-word reveal for statements. `muted` words render in the secondary colour. */
export function SplitWords({ text, muted = '', as = 'p', className = '', stagger = 32 }) {
  const Tag = as
  const ref = useRef(null)
  const inView = useInView(ref)
  const words = [...text.split(' ').map((w) => [w, false]), ...(muted ? muted.split(' ').map((w) => [w, true]) : [])]
  return (
    <Tag ref={ref} className={`lp-words ${inView ? 'is-in' : ''} ${className}`} aria-label={`${text} ${muted}`.trim()}>
      {words.map(([w, m], i) => (
        <span key={i} aria-hidden="true" className={`lp-words__w ${m ? 'is-muted' : ''}`} style={{ '--d': `${i * stagger}ms` }}>
          {w}{' '}
        </span>
      ))}
    </Tag>
  )
}

/**
 * Writes scroll progress (0..1) of `ref` into the CSS variable `--p` on that
 * element, without React re-renders. start: element top at viewport bottom;
 * end: element bottom at `endAt` of the viewport height.
 */
export function useScrollProgress(ref, { endAt = 0.6 } = {}) {
  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    if (prefersReducedMotion()) {
      el.style.setProperty('--p', '1')
      return undefined
    }
    let raf = 0
    const update = () => {
      raf = 0
      const r = el.getBoundingClientRect()
      const vh = window.innerHeight
      const total = r.height + vh * (1 - endAt)
      const p = Math.min(1, Math.max(0, (vh - r.top) / total))
      el.style.setProperty('--p', p.toFixed(4))
    }
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(update) }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [ref, endAt])
}

/** Count up to a real numeric value once visible. */
export function CountUp({ value, duration = 1400, pad = 0 }) {
  const ref = useRef(null)
  const inView = useInView(ref)
  useEffect(() => {
    const el = ref.current
    if (!el || !inView) return undefined
    if (prefersReducedMotion()) {
      el.textContent = String(value).padStart(pad, '0')
      return undefined
    }
    let raf = 0
    const start = performance.now()
    const tick = (t) => {
      const k = Math.min(1, (t - start) / duration)
      const eased = 1 - Math.pow(1 - k, 4)
      el.textContent = String(Math.round(eased * value)).padStart(pad, '0')
      if (k < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [inView, value, duration, pad])
  return (
    <>
      <span ref={ref} aria-hidden="true">{String(0).padStart(pad, '0')}</span>
      <span className="sr-only">{value}</span>
    </>
  )
}

/** Smooth-scroll to a section id, accounting for the fixed navbar. */
export function scrollToId(id) {
  const el = document.getElementById(id)
  if (!el) return
  const top = el.getBoundingClientRect().top + window.scrollY - 72
  window.scrollTo({ top, behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
}
