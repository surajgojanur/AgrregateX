import Icon from '../components/ui/Icon'
import { CountUp, Reveal, SplitLines } from './motion'

/* ---------- Privacy & offline processing ---------- */
export function Privacy() {
  return (
    <section id="privacy" className="lp-section" aria-labelledby="privacy-title">
      <div className="lp-shell">
        <div className="lp-section__head">
          <Reveal><span className="lp-eyebrow">Privacy &amp; offline processing</span></Reveal>
          <SplitLines lines={['Know where your data goes', 'before you press generate.']} className="lp-h2" />
          <span id="privacy-title" className="sr-only">Privacy and offline processing</span>
        </div>
        <div className="lp-privacy">
          <Reveal y={36} className="lp-privacy__card is-local">
            <div className="lp-privacy__top">
              <span className="lp-privacy__icon"><Icon name="cpu" /></span>
              <div>
                <h3>Offline procedural mode</h3>
                <span className="lp-tag lp-tag--procedural">Default</span>
              </div>
            </div>
            <ul>
              <li><Icon name="check" /> Composites are generated locally by the built-in renderer.</li>
              <li><Icon name="check" /> No external image-generation API is required.</li>
              <li><Icon name="check" /> Trait extraction and refinement run on your machine.</li>
              <li><Icon name="check" /> The engine listens on 127.0.0.1 only.</li>
            </ul>
            <div className="lp-privacy__flow lp-mono" aria-hidden="true">
              <span>Description</span><i /><span>Local engine</span><i /><span>Composite</span>
            </div>
          </Reveal>
          <Reveal y={36} delay={120} className="lp-privacy__card is-remote">
            <div className="lp-privacy__top">
              <span className="lp-privacy__icon"><Icon name="cloud" /></span>
              <div>
                <h3>Optional hosted AI mode</h3>
                <span className="lp-tag lp-tag--ai">Off unless you configure it</span>
              </div>
            </div>
            <ul>
              <li><Icon name="alert" /> Sends a trait-based prompt, and any reference image you attach, to the provider.</li>
              <li><Icon name="alert" /> The provider’s own terms, retention and pricing apply.</li>
              <li><Icon name="info" /> Credentials stay in the backend environment, never in the browser.</li>
              <li><Icon name="info" /> The active mode is shown before you generate, and on every result.</li>
            </ul>
            <div className="lp-privacy__flow lp-mono" aria-hidden="true">
              <span>Description</span><i /><span>Local engine</span><i className="is-out" /><span>Provider</span>
            </div>
          </Reveal>
        </div>
        <Reveal delay={200}>
          <p className="lp-privacy__note">
            Don’t send sensitive descriptions or images to a hosted provider until you have checked which mode is active.
            Revelio makes no claims of encryption, certification or legal compliance.
          </p>
        </Reveal>
      </div>
    </section>
  )
}

/* ---------- Verifiable capabilities (instead of testimonials) ---------- */
const NUMBERS = [
  [20, 'facial traits in the editable profile'],
  [16, 'proportion controls in the editor'],
  [6, 'types of distinctive marks'],
  [3, 'export formats: PNG, JSON, report'],
]
const CAPS = [
  ['list', 'Editable facial attributes', 'Every trait shows whether it was described, extracted, edited or unknown.'],
  ['image', 'Procedural image generation', 'Deterministic vector rendering: the same profile always draws the same face.'],
  ['download', 'Local PNG export', 'Downloads come straight from the local engine.'],
  ['compare', 'Revision comparison', 'Drag-to-reveal and side-by-side views, with a trait diff.'],
  ['layers', 'Optional provider architecture', 'Hosted and local AI plug in behind one interface, clearly labelled.'],
]

export function Capabilities() {
  return (
    <section className="lp-section" aria-labelledby="caps-title">
      <div className="lp-shell">
        <Reveal y={40} scale={0.99} className="lp-caps">
          <span className="lp-eyebrow">Built around a practical workflow</span>
          <SplitLines lines={['No testimonials.', 'Just what the software does.']} className="lp-h2 lp-caps__title" />
          <span id="caps-title" className="sr-only">Capabilities</span>
          <ul className="lp-caps__numbers">
            {NUMBERS.map(([n, label], i) => (
              <Reveal as="li" key={label} delay={i * 90} y={20}>
                <span className="lp-caps__n"><CountUp value={n} pad={2} /></span>
                <span className="lp-caps__l">{label}</span>
              </Reveal>
            ))}
          </ul>
          <ul className="lp-caps__list">
            {CAPS.map(([icon, title, text], i) => (
              <Reveal as="li" key={title} delay={i * 70} y={18}>
                <Icon name={icon} />
                <div><b>{title}</b><span>{text}</span></div>
              </Reveal>
            ))}
          </ul>
          <p className="lp-caps__foot lp-mono">Counts reflect this build’s trait catalog.</p>
        </Reveal>
      </div>
    </section>
  )
}
