import { useRef } from 'react'
import Icon from '../components/ui/Icon'
import { canHover, Reveal, SplitLines, SplitWords, useScrollProgress } from './motion'

/* ---------- Statement (Lumora "About" word reveal) ---------- */
export function Statement() {
  return (
    <section className="lp-section lp-statement" aria-label="About Revelio">
      <div className="lp-shell lp-statement__grid">
        <Reveal className="lp-statement__side">
          <span className="lp-eyebrow">The product</span>
          <div className="lp-statement__glyph" aria-hidden="true"><Icon name="scan" strokeWidth={0.6} /></div>
          <p className="lp-faint">Built for investigators, forensic artists, and research and education demos.</p>
        </Reveal>
        <div>
          <SplitWords
            as="h2"
            className="lp-statement__text"
            text="Revelio turns what a witness remembers into a structured, editable facial profile and a stylised composite —"
            muted="and it is explicit about everything the witness did not say."
          />
          <Reveal delay={200} className="lp-statement__foot">
            <span className="lp-mono lp-faint">Unknown stays unknown · conflicts stay visible · every image says how it was made</span>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

/* ---------- Pill band (Lumora "We / Build / → / Better") ---------- */
export function Band() {
  const items = [
    ['Describe', 'light'],
    ['Extract', 'accent'],
    [null, 'dark'],
    ['Composite', 'ghost'],
  ]
  return (
    <section className="lp-band" aria-label="Workflow summary">
      <ul className="lp-shell lp-band__list">
        {items.map(([word, variant], i) => (
          <Reveal as="li" key={i} delay={i * 110} y={28}>
            <span className={`lp-band__pill is-${variant}`}>
              {word || <Icon name="arrowRight" strokeWidth={1.4} />}
              {!word && <span className="sr-only">then</span>}
            </span>
          </Reveal>
        ))}
      </ul>
    </section>
  )
}

/* ---------- Features ---------- */
function useSpotlight() {
  return {
    onPointerMove: (e) => {
      if (!canHover()) return
      const r = e.currentTarget.getBoundingClientRect()
      e.currentTarget.style.setProperty('--x', `${e.clientX - r.left}px`)
      e.currentTarget.style.setProperty('--y', `${e.clientY - r.top}px`)
    },
  }
}

const MINI = {
  describe: (
    <div className="lp-mini lp-mini--describe" aria-hidden="true">
      <span className="lp-mini__text">“…oval face, short curly dark hair, thick eyebrows…”</span>
      <Icon name="arrowRight" />
      <img src="/landing/demo-r1.webp" alt="" loading="lazy" />
    </div>
  ),
  extract: (
    <ul className="lp-mini lp-mini--chips" aria-hidden="true">
      <li className="lp-chip lp-chip--extracted">Face: <b>Oval</b></li>
      <li className="lp-chip lp-chip--extracted">Hair: <b>Short · dark</b></li>
      <li className="lp-chip lp-chip--extracted">Brows: <b>Thick</b></li>
      <li className="lp-chip lp-chip--unknown">Eyes: <b>unknown</b></li>
      <li className="lp-chip lp-chip--conflict">Eye colour: <b>blue / brown?</b></li>
    </ul>
  ),
  editor: (
    <div className="lp-mini lp-mini--sliders" aria-hidden="true">
      {['Jaw width', 'Eye spacing', 'Nose length'].map((l, i) => (
        <div key={l}><span>{l}</span><i style={{ '--v': `${[68, 42, 56][i]}%` }} /></div>
      ))}
    </div>
  ),
  refine: (
    <div className="lp-mini lp-mini--revs" aria-hidden="true">
      {['R1', 'R2', 'R3'].map((r, i) => (
        <span key={r} className={i === 2 ? 'is-on' : ''}><b className="lp-mono">{r}</b><em>{['Initial', 'Longer hair', 'Add full beard'][i]}</em></span>
      ))}
    </div>
  ),
  compare: (
    <div className="lp-mini lp-mini--compare" aria-hidden="true">
      <div className="lp-mini__split">
        <img src="/landing/demo-r1.webp" alt="" loading="lazy" />
        <img src="/landing/demo-r2.webp" alt="" loading="lazy" />
        <i />
      </div>
      <span className="lp-chip">PNG · JSON · Report</span>
    </div>
  ),
  offline: (
    <div className="lp-mini lp-mini--offline" aria-hidden="true">
      <span className="lp-mono"><i className="lp-dot lp-dot--ok" /> 127.0.0.1 · local engine</span>
      <span className="lp-mono"><i className="lp-dot" /> external API · not required</span>
    </div>
  ),
}

const FEATURES = [
  ['describe', 'text', 'Description to Composite', 'Convert a witness’s written description into structured facial attributes and a composite.'],
  ['extract', 'list', 'Facial Trait Extraction', 'Organise descriptions into editable face shape, hair, eyebrows, eyes, nose, mouth and distinctive marks.'],
  ['editor', 'sliders', 'Interactive Facial Editor', 'Adjust supported facial characteristics and see the changes immediately in procedural mode.'],
  ['refine', 'history', 'Iterative Refinement', 'Revise descriptions, update facial traits, and keep every previous version as a revision.'],
  ['compare', 'compare', 'Compare and Export', 'Compare revisions with a drag-to-reveal view and download the composite as PNG, plus JSON and a report.'],
  ['offline', 'cpu', 'Offline-First Generation', 'Create procedural facial composites on your own machine, without relying on a paid API.'],
]

export function Features() {
  const spot = useSpotlight()
  return (
    <section id="features" className="lp-section" aria-labelledby="features-title">
      <div className="lp-shell">
        <div className="lp-section__head">
          <Reveal><span className="lp-eyebrow">Features</span></Reveal>
          <SplitLines lines={['Everything between a', 'description and a sketch.']} className="lp-h2" />
          <span id="features-title" className="sr-only">Features</span>
        </div>
        <ul className="lp-features">
          {FEATURES.map(([mini, icon, title, text], i) => (
            <Reveal as="li" key={title} delay={(i % 3) * 90} y={40}>
              <article className="lp-feature" {...spot}>
                <div className="lp-feature__icon"><Icon name={icon} /></div>
                <h3>{title}</h3>
                <p>{text}</p>
                {MINI[mini]}
              </article>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  )
}

/* ---------- How it works ---------- */
const STEPS = [
  ['01', 'Describe', 'Enter a witness description or use the guided trait form.', 'text'],
  ['02', 'Extract', 'Convert the description into structured facial attributes.', 'list'],
  ['03', 'Generate', 'Create a procedural composite offline, or use an optional configured AI provider.', 'cpu'],
  ['04', 'Refine', 'Adjust features, compare revisions, and export the selected composite.', 'wand'],
]

export function Workflow() {
  const ref = useRef(null)
  useScrollProgress(ref, { endAt: 0.55 })
  return (
    <section id="how" className="lp-section lp-flow" aria-labelledby="how-title">
      <div className="lp-shell">
        <div className="lp-section__head">
          <Reveal><span className="lp-eyebrow">How it works</span></Reveal>
          <SplitLines lines={['Four steps,', 'one focused workspace.']} className="lp-h2" />
          <span id="how-title" className="sr-only">How it works</span>
        </div>
        <div ref={ref} className="lp-flow__wrap">
        <span className="lp-flow__track" aria-hidden="true"><span className="lp-flow__fill" /></span>
        <ol className="lp-flow__steps">
          {STEPS.map(([n, title, text, icon], i) => (
            <Reveal as="li" key={n} delay={i * 110} y={30} className="lp-flow__step" style={{ '--k': i / (STEPS.length - 1) }}>
              <span className="lp-flow__node"><Icon name={icon} /></span>
              <span className="lp-mono lp-flow__n">Step {n}</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </Reveal>
          ))}
        </ol>
        </div>
      </div>
    </section>
  )
}
