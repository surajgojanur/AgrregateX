import { useEffect, useRef, useState } from 'react'
import { LogoMark } from '../components/brand/Logo'
import Icon from '../components/ui/Icon'
import { canHover, prefersReducedMotion, Reveal, scrollToId, SplitLines, useIntroReady } from './motion'
import { createPlayOrb } from './playOrb'

const R1 = '/landing/demo-r1.webp'
const R2 = '/landing/demo-r2.webp'

// Traits of the fictional demo profile (extracted from the description, then refined).
const DEMO_TRAITS = [
  ['Face shape', 'Oval', 'extracted'],
  ['Hair', 'Curly · dark', 'extracted'],
  ['Eyebrows', 'Thick', 'extracted'],
  ['Eyes', 'Dark · deep-set', 'extracted'],
  ['Nose', 'Straight', 'extracted'],
  ['Hair length', 'Collar-length', 'manual'],
  ['Facial hair', 'Full beard', 'manual'],
]

/**
 * Lumora-style liquid reveal: base image always visible; the pointer paints a
 * soft, decaying brush trail of the second image on a canvas above it.
 */
function LiquidComposite({ base, reveal, onModeChange }) {
  const wrap = useRef(null)
  const canvas = useRef(null)
  const [interactive] = useState(() => canHover() && !prefersReducedMotion())

  useEffect(() => {
    if (!interactive) return undefined
    const el = wrap.current
    const cv = canvas.current
    const ctx = cv.getContext('2d')
    const img = new Image()
    img.src = reveal
    const BRUSH = 70
    const DECAY = 0.03
    let dpr = Math.min(window.devicePixelRatio || 1, 2)
    let cover = document.createElement('canvas')
    let brush = document.createElement('canvas')
    let radius = BRUSH * dpr
    let points = []
    let last = null
    let idle = 0
    let raf = 0

    let alive = true
    const layout = () => {
      if (!alive || !cover || !brush) return
      const r = el.getBoundingClientRect()
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      cv.width = Math.round(r.width * dpr)
      cv.height = Math.round(r.height * dpr)
      radius = BRUSH * dpr
      cover.width = cv.width
      cover.height = cv.height
      if (img.complete && img.naturalWidth) {
        const c = cover.getContext('2d')
        const s = Math.max(cv.width / img.naturalWidth, cv.height / img.naturalHeight)
        const w = img.naturalWidth * s
        const h = img.naturalHeight * s
        c.drawImage(img, (cv.width - w) / 2, (cv.height - h) / 2, w, h)
      }
      const d = Math.ceil(radius * 2)
      brush.width = d
      brush.height = d
    }

    const stamp = (x, y) => {
      const d = brush.width
      const c = d / 2
      const b = brush.getContext('2d')
      b.globalCompositeOperation = 'source-over'
      b.clearRect(0, 0, d, d)
      const g = b.createRadialGradient(c, c, 0, c, c, c)
      g.addColorStop(0, 'rgba(255,255,255,1)')
      g.addColorStop(0.55, 'rgba(255,255,255,0.82)')
      g.addColorStop(1, 'rgba(255,255,255,0)')
      b.fillStyle = g
      b.fillRect(0, 0, d, d)
      b.globalCompositeOperation = 'source-in'
      b.drawImage(cover, x - c, y - c, d, d, 0, 0, d, d)
      ctx.globalCompositeOperation = 'source-over'
      ctx.drawImage(brush, x - c, y - c)
    }

    const tick = () => {
      raf = 0
      if (!alive) return
      const drawing = points.length > 0
      if (drawing) idle = 0
      else idle += 1
      const fade = drawing ? DECAY : Math.min(DECAY + idle * 0.004, 0.5)
      ctx.globalCompositeOperation = 'destination-out'
      ctx.fillStyle = `rgba(0,0,0,${fade})`
      ctx.fillRect(0, 0, cv.width, cv.height)
      if (drawing) {
        for (const [x, y] of points) stamp(x, y)
        points = []
      }
      if (idle > 120) {
        ctx.clearRect(0, 0, cv.width, cv.height)
        return
      }
      raf = requestAnimationFrame(tick)
    }

    const onMove = (e) => {
      const r = el.getBoundingClientRect()
      const x = (e.clientX - r.left) * dpr
      const y = (e.clientY - r.top) * dpr
      if (last) {
        const dist = Math.hypot(x - last[0], y - last[1])
        const step = Math.max(radius * 0.3, 1)
        const n = Math.min(Math.ceil(dist / step), 60)
        for (let i = 1; i <= n; i++) points.push([last[0] + ((x - last[0]) * i) / n, last[1] + ((y - last[1]) * i) / n])
      } else points.push([x, y])
      last = [x, y]
      if (!raf) raf = requestAnimationFrame(tick)
    }
    const onLeave = () => { last = null }

    img.onload = layout
    layout()
    const ro = new ResizeObserver(layout)
    ro.observe(el)
    el.addEventListener('pointermove', onMove)
    el.addEventListener('pointerleave', onLeave)
    return () => {
      alive = false
      img.onload = null
      cancelAnimationFrame(raf)
      ro.disconnect()
      el.removeEventListener('pointermove', onMove)
      el.removeEventListener('pointerleave', onLeave)
      cover = null
      brush = null
    }
  }, [interactive, reveal])

  const [showReveal, setShowReveal] = useState(false)
  useEffect(() => onModeChange?.(showReveal ? 'R1' : 'R2'), [showReveal, onModeChange])

  return (
    <div ref={wrap} className={`lp-liquid ${interactive ? 'is-interactive' : ''}`}>
      <img className="lp-liquid__base" src={base} alt="Pencil-style demonstration sketch, revision 2, of a fictional profile" width="900" height="1125" fetchPriority="high" />
      <img className={`lp-liquid__alt ${showReveal ? 'is-on' : ''}`} src={reveal} alt="" aria-hidden="true" loading="lazy" />
      {interactive && <canvas ref={canvas} className="lp-liquid__canvas" aria-hidden="true" />}
      {!interactive && (
        <button type="button" className="lp-liquid__toggle" onClick={() => setShowReveal((v) => !v)} aria-pressed={showReveal}>
          <Icon name="compare" /> {showReveal ? 'Show revision 2' : 'Show revision 1'}
        </button>
      )}
    </div>
  )
}

export default function Hero() {
  const ready = useIntroReady()
  const section = useRef(null)
  const [mode, setMode] = useState('R2')

  // Cursor-following light + subtle parallax, throttled to one write per frame.
  useEffect(() => {
    const el = section.current
    if (!el || prefersReducedMotion()) return undefined
    let raf = 0
    let mx = 0.5
    let my = 0.3
    let sy = null // eased parallax offset; follows the scroll target instead of jumping to it
    const orb = createPlayOrb({ section: el, copy: el.querySelector('.lp-hero__copy') })
    const apply = () => {
      raf = 0
      el.style.setProperty('--mx', `${(mx * 100).toFixed(2)}%`)
      el.style.setProperty('--my', `${(my * 100).toFixed(2)}%`)
      const progress = Math.min(window.scrollY, 900) / 900
      const target = progress * progress * (3 - 2 * progress) * 900
      sy = sy === null ? target : sy + (target - sy) * 0.06
      if (Math.abs(target - sy) < 0.4) sy = target
      else raf = requestAnimationFrame(apply)
      el.style.setProperty('--sy', sy.toFixed(1))
      const shrink = Math.min(sy / 560, 1)
      el.style.setProperty('--shrink', shrink.toFixed(3))
      orb.update(shrink, sy)
    }
    const onMove = (e) => {
      const r = el.getBoundingClientRect()
      mx = (e.clientX - r.left) / r.width
      my = (e.clientY - r.top) / r.height
      if (!raf) raf = requestAnimationFrame(apply)
    }
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(apply) }
    if (canHover()) el.addEventListener('pointermove', onMove)
    window.addEventListener('scroll', onScroll, { passive: true })
    apply()
    return () => {
      cancelAnimationFrame(raf)
      orb.destroy()
      el.removeEventListener('pointermove', onMove)
      window.removeEventListener('scroll', onScroll)
    }
  }, [])

  return (
    <section id="platform" ref={section} className="lp-hero" aria-labelledby="hero-title">
      <div className="lp-hero__grid" aria-hidden="true" />
      <div className="lp-hero__light" aria-hidden="true" />
      <div className="lp-hero__watermark" aria-hidden="true">REVELIO</div>

      <div className="lp-shell lp-hero__inner">
        <div className="lp-hero__copy">
          <Reveal gate={ready} delay={150} y={10}>
            <span className="lp-eyebrow">AI-assisted digital forensics</span>
          </Reveal>
          <SplitLines
            as="h1"
            gate={ready}
            delay={220}
            stagger={120}
            className="lp-hero__title"
            lines={['Turn witness', 'descriptions into', 'visual composites.']}
          />
          <span id="hero-title" className="sr-only">Turn witness descriptions into visual composites.</span>
          <Reveal gate={ready} delay={600} y={14}>
            <p className="lp-hero__lead">
              Transform verbal observations into editable facial composites, refine the details, and compare versions in one focused workspace.
            </p>
          </Reveal>
          <Reveal gate={ready} delay={720} y={14} className="lp-hero__ctas">
            <a href="/app#/new" className="lp-btn lp-btn--primary lp-btn--lg">
              Create a Sketch <span className="lp-btn__badge"><Icon name="arrowRight" /></span>
            </a>
            <button type="button" className="lp-btn lp-btn--ghost lp-btn--lg" onClick={() => scrollToId('demo')}>
              Explore the Platform
            </button>
          </Reveal>
          <Reveal gate={ready} delay={860} y={10} className="lp-hero__facts">
            <span><Icon name="cpu" /> Offline procedural renderer</span>
            <span><Icon name="lock" /> No API key required</span>
            <span><Icon name="shield" /> Every result labelled by method</span>
          </Reveal>
        </div>

        <Reveal gate={ready} delay={380} y={28} scale={0.97} className="lp-case">
          <div className="lp-case__frame">
            <span className="lp-case__corner lp-case__corner--tl" aria-hidden="true" />
            <span className="lp-case__corner lp-case__corner--tr" aria-hidden="true" />
            <span className="lp-case__corner lp-case__corner--bl" aria-hidden="true" />
            <span className="lp-case__corner lp-case__corner--br" aria-hidden="true" />
            <div className="lp-case__top lp-mono">
              <span>RV-DEMO-0001 · {mode}</span>
              <span className="lp-case__demo">Demo · fictional profile</span>
            </div>
            <div className="lp-case__image">
              <LiquidComposite base={R2} reveal={R1} onModeChange={setMode} />
              <span className="lp-case__scan" aria-hidden="true" />
              <span className="lp-case__hint lp-mono" aria-hidden="true">Move to reveal R1</span>
            </div>
            <div className="lp-case__meta lp-mono">
              <span><b>Method</b> AI sketch</span>
              <span><b>Output</b> 900 × 1125 PNG</span>
              <span className="lp-case__notai">AI-generated · fictional</span>
            </div>
          </div>

          <aside className="lp-traits" aria-label="Demo trait profile">
            <div className="lp-traits__head">
              <span className="lp-mono">Trait profile</span>
              <span className="lp-mono lp-traits__count">7 known · 13 unknown</span>
            </div>
            <ul>
              {DEMO_TRAITS.map(([k, v, src], i) => (
                <li key={k} style={{ '--i': i }}>
                  <span className="lp-traits__k">{k}</span>
                  <span className="lp-traits__v">{v}</span>
                  <span className={`lp-tag lp-tag--${src}`}>{src}</span>
                </li>
              ))}
            </ul>
          </aside>

          <svg className="lp-case__links" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <path d="M58 30 C 66 30, 70 24, 80 24" />
            <path d="M54 52 C 66 52, 70 46, 80 46" />
            <path d="M62 58 C 70 62, 72 66, 80 68" />
          </svg>
        </Reveal>
      </div>

      <Reveal gate={ready} delay={950} y={0} className="lp-shell lp-hero__bar lp-mono">
        <span><LogoMark size={16} /> Offline-first by design</span>
        <span className="lp-hide-sm">Procedural renderer · v1 · deterministic</span>
        <button type="button" onClick={() => scrollToId('demo')}>Scroll to explore <span aria-hidden="true">↓</span></button>
      </Reveal>
    </section>
  )
}
