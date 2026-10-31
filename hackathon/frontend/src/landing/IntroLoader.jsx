import { useEffect, useRef, useState } from 'react'
import { BrandLogo } from '../components/brand/Logo'
import { markIntroSeen } from './motion'

const FILL_MS = 1100
const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)

// Short, skippable intro (Lumora-style count 000 → 100, then slide up).
export default function IntroLoader({ onDone }) {
  const countRef = useRef(null)
  const barRef = useRef(null)
  const [leaving, setLeaving] = useState(false)
  const [gone, setGone] = useState(false)
  const doneRef = useRef(onDone)
  const finished = useRef(false)

  useEffect(() => {
    doneRef.current = onDone
  })

  const finish = () => {
    if (finished.current) return
    finished.current = true
    markIntroSeen()
    setLeaving(true)
    doneRef.current?.()
    setTimeout(() => setGone(true), 750)
  }

  useEffect(() => {
    document.documentElement.classList.add('lp-locked')
    let raf = 0
    const start = performance.now()
    const tick = (t) => {
      const k = Math.min(1, (t - start) / FILL_MS)
      const v = Math.round(easeInOutCubic(k) * 100)
      if (countRef.current) countRef.current.textContent = String(v).padStart(3, '0')
      if (barRef.current) barRef.current.style.transform = `scaleX(${v / 100})`
      if (k < 1) raf = requestAnimationFrame(tick)
      else finish()
    }
    raf = requestAnimationFrame(tick)
    const onKey = (e) => (e.key === 'Escape' || e.key === 'Enter') && finish()
    window.addEventListener('keydown', onKey)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('keydown', onKey)
      document.documentElement.classList.remove('lp-locked')
    }
  }, [])

  useEffect(() => {
    if (leaving) document.documentElement.classList.remove('lp-locked')
  }, [leaving])

  if (gone) return null
  return (
    <div className={`lp-intro ${leaving ? 'is-leaving' : ''}`} role="status" aria-label="Loading Revelio">
      <div className="lp-intro__center">
        <div className="lp-intro__brand">
          <BrandLogo height={84} animated />
        </div>
        <p className="lp-intro__status">Initializing forensic workspace</p>
      </div>
      <div className="lp-intro__progress">
        <div className="lp-intro__track"><span ref={barRef} /></div>
        <div className="lp-intro__row">
          <span>Loading</span>
          <span ref={countRef} className="lp-mono">000</span>
        </div>
      </div>
      <button type="button" className="lp-intro__skip" onClick={finish}>Skip intro</button>
    </div>
  )
}
