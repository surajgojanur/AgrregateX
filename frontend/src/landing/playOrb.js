// Small ball that the hero orb turns into once it has shrunk on scroll. With a mouse
// it chases the cursor; otherwise (touch, or the cursor has left the page) it drifts
// toward the emptiest part of the viewport and bounces off the edges and off visible
// content, and can be dragged, thrown or tapped.

const R = 5
const MIN_SPEED = 1.1
const MAX_SPEED = 9
const RESTITUTION = 0.88
const OBSTACLES = 'h1, h2, h3, h4, p, li, img, canvas, svg, button, a, input, textarea, select, figure, blockquote, pre, table, .lp-case__frame, .lp-traits'

function circleRect(x, y, r) {
  const cx = Math.max(r.left, Math.min(x, r.right))
  const cy = Math.max(r.top, Math.min(y, r.bottom))
  return [x - cx, y - cy]
}

export function createPlayOrb({ section, copy }) {
  const el = document.createElement('div')
  el.className = 'lp-playorb'
  el.setAttribute('aria-hidden', 'true')
  document.body.appendChild(el)

  let mode = 'off' // off | free | home
  let x = 0
  let y = 0
  let vx = 0
  let vy = 0
  let tx = 0
  let ty = 0
  let squashX = 0
  let squashY = 0
  let pop = 0 // 1 right after a hop, eases back to 0 as the ball grows in again
  let sy = 0
  let frame = 0
  let raf = 0
  let last = 0
  let nodes = []
  let rects = []
  let top = 0 // bottom of the fixed site header, used as the ceiling
  let drag = null
  let cursor = null // last mouse position while it is over the page

  const home = () => {
    const r = copy.getBoundingClientRect()
    return [r.left + r.width * 0.48 + sy * 0.3, r.top + r.height * 0.48 + sy * 0.4]
  }

  const collect = () => {
    // Hidden menus and not-yet-revealed content take up layout space but are not visible.
    const shown = (n) => !n.checkVisibility || n.checkVisibility({ opacityProperty: true, visibilityProperty: true })
    nodes = [...document.querySelectorAll(OBSTACLES)].filter((n) => !n.closest('.lp-hero__watermark') && shown(n))
  }

  const measure = () => {
    const W = window.innerWidth
    const H = window.innerHeight
    const big = W * H * 0.55
    const bar = document.querySelector('.lp-nav')?.getBoundingClientRect()
    top = bar && bar.top <= 1 && bar.height < H * 0.3 ? Math.max(bar.bottom, 0) : 0
    rects = []
    for (const n of nodes) {
      const r = n.getBoundingClientRect()
      if (r.width < 2 || r.height < 2 || r.bottom < top - 40 || r.top > H + 40 || r.right < 0 || r.left > W) continue
      if (r.width * r.height > big) continue
      rects.push(r)
    }
  }

  // Coarse grid search for the point furthest from any content or edge.
  const findSpace = () => {
    const W = window.innerWidth
    const H = window.innerHeight
    let best = -1
    for (let gx = 1; gx < 14; gx++) {
      for (let gy = 1; gy < 10; gy++) {
        const px = (W * gx) / 14
        const py = top + ((H - top) * gy) / 10
        let clear = Math.min(px, py - top, W - px, H - py)
        for (const r of rects) {
          const [dx, dy] = circleRect(px, py, r)
          clear = Math.min(clear, Math.hypot(dx, dy))
          if (clear <= best) break
        }
        // Slight preference for nearby space so the ball wanders instead of teleporting.
        const score = clear - Math.hypot(px - x, py - y) * 0.04
        if (score > best) { best = score; tx = px; ty = py }
      }
    }
  }

  const bounce = (nx, ny) => {
    const dot = vx * nx + vy * ny
    if (dot >= 0) return
    vx -= (1 + RESTITUTION) * dot * nx
    vy -= (1 + RESTITUTION) * dot * ny
    // A small random spin keeps rebounds from settling into a repeating loop.
    const t = (Math.random() - 0.5) * 0.25
    ;[vx, vy] = [vx * Math.cos(t) - vy * Math.sin(t), vx * Math.sin(t) + vy * Math.cos(t)]
    const hit = Math.min(Math.abs(dot) / 8, 1)
    squashX = Math.max(squashX, hit * Math.abs(nx))
    squashY = Math.max(squashY, hit * Math.abs(ny))
  }

  const step = (dt) => {
    const W = window.innerWidth
    const H = window.innerHeight
    const dx = tx - x
    const dy = ty - y
    const d = Math.hypot(dx, dy) || 1
    // Gentle pull that fades out near the target, so the ball bounces around open
    // space rather than pressing against whatever lies in the way.
    const pull = Math.min(Math.max((d - 80) / 400, 0), 1) * 0.05 * dt
    vx += (dx / d) * pull
    vy += (dy / d) * pull
    const damp = 0.996 ** dt
    vx *= damp
    vy *= damp
    let speed = Math.hypot(vx, vy)
    if (speed < MIN_SPEED) {
      const a = speed ? Math.atan2(vy, vx) : Math.random() * Math.PI * 2
      vx = Math.cos(a) * MIN_SPEED
      vy = Math.sin(a) * MIN_SPEED
      speed = MIN_SPEED
    } else if (speed > MAX_SPEED) {
      vx *= MAX_SPEED / speed
      vy *= MAX_SPEED / speed
    }
    x += vx * dt
    y += vy * dt

    for (const r of rects) {
      const [ox, oy] = circleRect(x, y, r)
      const dist = Math.hypot(ox, oy)
      if (dist >= R) continue
      if (dist > 0) {
        x += (ox / dist) * (R - dist)
        y += (oy / dist) * (R - dist)
        bounce(ox / dist, oy / dist)
      } else {
        // Content scrolled over the ball: leave through the nearest side.
        const out = [[x - r.left + R, -1, 0], [r.right - x + R, 1, 0], [y - r.top + R, 0, -1], [r.bottom - y + R, 0, 1]]
          .filter(([len, nx, ny]) => x + nx * len >= R && x + nx * len <= W - R && y + ny * len >= top + R && y + ny * len <= H - R)
          .sort((a, b) => a[0] - b[0])
        if (!out.length) {
          // Squeezed by scrolling content with nowhere to go: pop over to open space.
          findSpace()
          x = tx
          y = ty
          pop = 1
          return
        }
        const [len, nx, ny] = out[0]
        x += nx * len
        y += ny * len
        bounce(nx, ny)
      }
    }

    walls(W, H)
  }

  const walls = (W, H) => {
    if (x < R) { x = R; bounce(1, 0) }
    if (x > W - R) { x = W - R; bounce(-1, 0) }
    if (y < top + R) { y = top + R; bounce(0, 1) }
    if (y > H - R) { y = H - R; bounce(0, -1) }
  }

  // Springy follow that trails just below-right of the pointer, so the ball never
  // sits on top of whatever is about to be clicked.
  const chase = (dt) => {
    vx += (cursor[0] + 16 - x) * 0.018 * dt
    vy += (cursor[1] + 16 - y) * 0.018 * dt
    const damp = 0.85 ** dt
    vx *= damp
    vy *= damp
    x += vx * dt
    y += vy * dt
    walls(window.innerWidth, window.innerHeight)
  }

  const render = () => {
    const sx = 1 + squashY * 0.22 - squashX * 0.28
    const sv = 1 + squashX * 0.22 - squashY * 0.28
    const grow = 1 - pop
    el.style.transform = `translate3d(${(x - R).toFixed(1)}px, ${(y - R).toFixed(1)}px, 0) scale(${(sx * grow).toFixed(3)}, ${(sv * grow).toFixed(3)})`
  }

  const loop = (now) => {
    raf = 0
    const dt = last ? Math.min((now - last) / 16.67, 3) : 1
    last = now
    frame += 1
    squashX *= 0.8 ** dt
    squashY *= 0.8 ** dt
    pop *= 0.88 ** dt
    if (mode === 'home') {
      const [hx, hy] = home()
      x += (hx - x) * Math.min(0.16 * dt, 1)
      y += (hy - y) * Math.min(0.16 * dt, 1)
      if (Math.hypot(hx - x, hy - y) < 3) {
        mode = 'off'
        el.classList.remove('is-on')
        section.classList.remove('is-orb-free')
        last = 0
        return
      }
    } else if (cursor) {
      if (frame % 4 === 0) measure()
      chase(dt)
    } else if (!drag) {
      if (frame % 60 === 0) collect()
      if (frame % 4 === 0) measure()
      if (frame % 50 === 0) findSpace()
      step(dt)
    }
    render()
    raf = requestAnimationFrame(loop)
  }

  const start = () => { if (!raf) raf = requestAnimationFrame(loop) }

  const release = () => {
    collect()
    measure()
    const [hx, hy] = home()
    x = Math.max(R, Math.min(hx, window.innerWidth - R))
    y = Math.max(top + R, Math.min(hy, window.innerHeight - R))
    const a = Math.PI * (0.15 + Math.random() * 0.25)
    vx = Math.cos(a) * 4
    vy = Math.sin(a) * 4
    findSpace()
    mode = 'free'
    render()
    el.classList.add('is-on')
    section.classList.add('is-orb-free')
    start()
  }

  const onDown = (e) => {
    if (mode !== 'free') return
    el.setPointerCapture(e.pointerId)
    drag = { id: e.pointerId, ox: e.clientX - x, oy: e.clientY - y, px: e.clientX, py: e.clientY, t: e.timeStamp, moved: 0 }
    vx = 0
    vy = 0
    el.classList.add('is-grabbed')
  }
  const onMove = (e) => {
    if (!drag || e.pointerId !== drag.id) return
    const dt = Math.max((e.timeStamp - drag.t) / 16.67, 0.5)
    vx = vx * 0.4 + ((e.clientX - drag.px) / dt) * 0.6
    vy = vy * 0.4 + ((e.clientY - drag.py) / dt) * 0.6
    drag.moved += Math.hypot(e.clientX - drag.px, e.clientY - drag.py)
    drag.px = e.clientX
    drag.py = e.clientY
    drag.t = e.timeStamp
    x = Math.max(R, Math.min(e.clientX - drag.ox, window.innerWidth - R))
    y = Math.max(top + R, Math.min(e.clientY - drag.oy, window.innerHeight - R))
  }
  const onUp = (e) => {
    if (!drag || e.pointerId !== drag.id) return
    // A tap without a drag gives the ball a playful kick in a random direction.
    if (drag.moved < 4) {
      const a = Math.random() * Math.PI * 2
      vx = Math.cos(a) * 7
      vy = Math.sin(a) * 7
    }
    drag = null
    el.classList.remove('is-grabbed')
    findSpace()
  }
  el.addEventListener('pointerdown', onDown)
  el.addEventListener('pointermove', onMove)
  el.addEventListener('pointerup', onUp)
  el.addEventListener('pointercancel', onUp)

  const onResize = () => { if (mode === 'free') { collect(); measure(); findSpace() } }
  window.addEventListener('resize', onResize)

  const onPointer = (e) => {
    if (e.pointerType !== 'mouse' && e.pointerType !== 'pen') return
    cursor = [e.clientX, e.clientY]
    el.classList.add('is-chasing')
  }
  const onPointerOut = (e) => {
    if (e.relatedTarget) return
    cursor = null
    el.classList.remove('is-chasing')
    if (mode === 'free') findSpace()
  }
  window.addEventListener('pointermove', onPointer, { passive: true })
  document.addEventListener('pointerout', onPointerOut)
  window.addEventListener('blur', onPointerOut)

  return {
    update(shrink, offset) {
      sy = offset
      if (mode !== 'free' && shrink >= 0.99) release()
      else if (mode === 'free' && shrink < 0.85) {
        mode = 'home'
        drag = null
        el.classList.remove('is-grabbed')
        start()
      }
    },
    destroy() {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('pointermove', onPointer)
      document.removeEventListener('pointerout', onPointerOut)
      window.removeEventListener('blur', onPointerOut)
      section.classList.remove('is-orb-free')
      el.remove()
    },
  }
}
