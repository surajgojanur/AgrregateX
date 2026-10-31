import { BrandLogo } from '../components/brand/Logo'
import Icon from '../components/ui/Icon'
import { REPO_URL } from './constants'
import { Reveal, scrollToId, SplitLines } from './motion'

const FAQ = [
  ['Is Revelio free?', 'Yes. Everything in this build is free to run on your own machine. The Pro and Team plans on this page are proposals only: no payments are taken, and those features are not built yet.'],
  ['Can I generate sketches without an API key?', 'Yes. The offline procedural renderer is the default generator and needs no API key and no external service.'],
  ['Does offline mode need an internet connection?', 'Not after installation. Trait extraction, refinement, rendering, saving, comparison and export all run against the local engine on 127.0.0.1. Without internet, the interface only falls back from web fonts to system fonts.'],
  ['How realistic are procedural composites?', 'They are stylised, monochrome drawings assembled from vector facial features. They are not photorealistic forensic reconstructions, and they do not have the realism of advanced image-generation models.'],
  ['Can I use a hosted AI model?', 'Optionally. A Google Gemini provider can be enabled in the backend environment with your own key. It is off by default, it sends a trait-based prompt to Google, usage may be billed, and it has been tested against a mocked API only. AI results are always labelled AI-generated.'],
  ['What happens to uploaded reference images?', 'Reference images are only accepted for a provider that supports them (currently the optional hosted provider). They are validated, re-encoded to strip metadata, sent with that single request, and never stored. Revelio performs no face recognition or identity matching.'],
  ['Can I export my sketches?', 'Yes. Every revision can be downloaded as a PNG, and each sketch can be exported as JSON or as a printable report that includes the disclaimer.'],
  ['Is a generated composite proof of identity?', 'No. A composite is an investigative aid. It is not proof of identity and must never be treated as a definitive identification of any person.'],
]

export function Faq() {
  return (
    <section id="faq" className="lp-section" aria-labelledby="faq-title">
      <div className="lp-shell lp-faq">
        <div className="lp-faq__head">
          <Reveal><span className="lp-eyebrow">FAQ</span></Reveal>
          <SplitLines lines={['Questions,', 'answered plainly.']} className="lp-h2" />
          <span id="faq-title" className="sr-only">Frequently asked questions</span>
        </div>
        <div className="lp-faq__list">
          {FAQ.map(([q, a], i) => (
            <Reveal key={q} delay={i * 50} y={18}>
              <details className="lp-faq__item">
                <summary>
                  <span className="lp-mono lp-faq__n">{String(i + 1).padStart(2, '0')}</span>
                  <span className="lp-faq__q">{q}</span>
                  <span className="lp-faq__icon" aria-hidden="true"><Icon name="plus" /></span>
                </summary>
                <div className="lp-faq__a"><p>{a}</p></div>
              </details>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

export function FinalCta() {
  return (
    <section className="lp-section lp-final" aria-labelledby="final-title">
      <div className="lp-shell">
        <Reveal y={40} scale={0.98} className="lp-final__card">
          <div className="lp-final__grid" aria-hidden="true" />
          <div className="lp-final__glow" aria-hidden="true" />
          <SplitLines as="h2" lines={['Start with a description.', 'Refine every detail.']} className="lp-final__title" stagger={120} />
          <span id="final-title" className="sr-only">Start with a description. Refine every detail.</span>
          <Reveal delay={260}>
            <p className="lp-final__lead">Explore the offline composite workflow and build your first facial composite.</p>
          </Reveal>
          <Reveal delay={380}>
            <a href="/app" className="lp-btn lp-btn--primary lp-btn--lg">
              Launch Revelio <span className="lp-btn__badge"><Icon name="arrowRight" /></span>
            </a>
          </Reveal>
        </Reveal>
      </div>
    </section>
  )
}

const FOOT_COLS = [
  ['Product', [['Platform', 'platform'], ['Features', 'features'], ['How it works', 'how'], ['Live demo', 'demo']]],
  ['Workspace', [['Open Workspace', '/app'], ['New sketch', '/app#/new'], ['Sketch library', '/app#/library'], ['Compare sketches', '/app#/compare']]],
  ['Information', [['Pricing', 'pricing'], ['Privacy & offline', 'privacy'], ['FAQ', 'faq'], ['GitHub repository', REPO_URL]]],
]

export function Footer() {
  const year = new Date().getFullYear()
  return (
    <footer className="lp-footer">
      <div className="lp-shell lp-footer__inner">
        <div className="lp-footer__cols">
          <div className="lp-footer__brand">
            <span className="lp-brand"><BrandLogo height={52} /></span>
            <p>From Witness Description to Forensic Sketch. An offline-first workspace for building editable, investigative facial composites.</p>
          </div>
          {FOOT_COLS.map(([title, links]) => (
            <nav key={title} aria-label={title}>
              <h4>{title}</h4>
              <ul>
                {links.map(([label, target]) => (
                  <li key={label}>
                    {target.startsWith('/') || target.startsWith('http') ? (
                      <a href={target} {...(target.startsWith('http') ? { target: '_blank', rel: 'noreferrer' } : {})}>
                        {label}{target.startsWith('http') && <Icon name="external" />}
                      </a>
                    ) : (
                      <a href={`#${target}`} onClick={(e) => { e.preventDefault(); scrollToId(target) }}>{label}</a>
                    )}
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
        <p className="lp-footer__disclaimer">
          <Icon name="shield" />
          Revelio produces investigative facial composites. Generated images are not proof of identity and must not be treated as definitive identification.
        </p>
        <div className="lp-footer__legal">
          <span>© {year} Revelio · Built for HackFest 2026 by team SSDNexus (T1-20)</span>
          <span className="lp-mono">Procedural renderer v1 · offline-first</span>
        </div>
      </div>
      <div className="lp-footer__mark" aria-hidden="true">REVELIO</div>
    </footer>
  )
}
