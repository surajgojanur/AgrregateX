import { useRef, useState } from 'react'
import './CompareSlider.css'

const STEP = 5
const KEYS = { ArrowLeft: -STEP, ArrowDown: -STEP, ArrowRight: STEP, ArrowUp: STEP, PageDown: -20, PageUp: 20 }

// Drag-to-reveal comparison. Keyboard: arrows (Shift for larger steps), Page Up/Down, Home/End.
const CompareSlider = ({ before, after, beforeLabel, afterLabel }) => {
  const [pos, setPos] = useState(50)
  const [dragging, setDragging] = useState(false)
  const ref = useRef(null)

  const move = (clientX) => {
    const r = ref.current.getBoundingClientRect()
    setPos(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)))
  }
  const onKeyDown = (e) => {
    let next = null
    if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = 100
    else if (KEYS[e.key]) next = pos + KEYS[e.key] * (e.shiftKey ? 2 : 1)
    if (next === null) return
    e.preventDefault()
    setPos(Math.max(0, Math.min(100, next)))
  }
  const shown = Math.round(pos)

  return (
    <div
      ref={ref}
      className={`compare ${dragging ? 'is-dragging' : ''}`}
      onPointerDown={(e) => { setDragging(true); e.currentTarget.setPointerCapture(e.pointerId); move(e.clientX) }}
      onPointerMove={(e) => dragging && move(e.clientX)}
      onPointerUp={() => setDragging(false)}
      onPointerCancel={() => setDragging(false)}
    >
      <img className="compare__img" src={after} alt={afterLabel} draggable={false} />
      <div className="compare__before" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
        <img className="compare__img" src={before} alt={beforeLabel} draggable={false} />
      </div>
      <span className="compare__tag compare__tag--l mono">{beforeLabel}</span>
      <span className="compare__tag compare__tag--r mono">{afterLabel}</span>
      <div
        className="compare__handle"
        style={{ left: `${pos}%` }}
        role="slider"
        tabIndex={0}
        aria-label="Comparison divider"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={shown}
        aria-valuetext={`${shown}% ${beforeLabel} shown, ${100 - shown}% ${afterLabel} shown`}
        onKeyDown={onKeyDown}
      >
        <span className="compare__grip" />
        <span className="compare__pos mono" aria-hidden="true">{shown}%</span>
      </div>
    </div>
  )
}

export default CompareSlider
