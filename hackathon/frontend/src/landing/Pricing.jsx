import { useEffect, useRef, useState } from 'react'
import Icon from '../components/ui/Icon'
import { Reveal, SplitLines } from './motion'

import { REPO_URL } from './constants'

const PLANS = [
  {
    id: 'free', name: 'Free', price: '₹0', period: 'forever', state: 'Available now',
    blurb: 'Everything in this build, on your own machine.',
    features: ['Procedural facial-composite generation', 'Facial-feature editor', 'PNG export', 'Basic sketch history', 'Offline-first workflow', 'No API key required for procedural generation'],
    cta: 'Start Free',
  },
  {
    id: 'pro', name: 'Pro', price: '₹499', period: '/month', state: 'Coming soon',
    blurb: 'Proposed for individual investigators and artists.',
    features: ['Extended sketch history', 'Advanced comparison', 'Additional editing workflows', 'Optional AI-provider integrations', 'Export enhancements'],
    cta: 'Join Waitlist',
  },
  {
    id: 'team', name: 'Team', price: '₹1,999', period: '/month', state: 'Planned',
    blurb: 'Proposed for teams reviewing composites together.',
    features: ['Shared workspaces', 'Team revision history', 'Collaborative review', 'Administrative controls', 'Extended audit history'],
    cta: 'Explore Team Plan',
  },
]

const ROWS = [
  ['Procedural generation', 'Implemented', ['yes', 'planned', 'planned']],
  ['Offline operation', 'Implemented', ['yes', 'planned', 'planned']],
  ['Facial editing', 'Implemented', ['yes', 'planned', 'planned']],
  ['PNG export', 'Implemented', ['yes', 'planned', 'planned']],
  ['Revision history', 'Implemented (basic)', ['Basic', 'Extended · planned', 'Team · planned']],
  ['AI-provider support', 'Optional, bring your own key', ['Optional · BYO key', 'Integrations · planned', 'planned']],
  ['Collaboration', 'Not implemented', ['no', 'no', 'planned']],
]

function Cell({ v }) {
  if (v === 'yes') return <span className="lp-cmp__yes"><Icon name="check" strokeWidth={2.2} /><span className="sr-only">Included</span></span>
  if (v === 'no') return <span className="lp-cmp__no" aria-label="Not included">—</span>
  if (v === 'planned') return <span className="lp-tag lp-tag--planned">Planned</span>
  return <span className={`lp-cmp__text ${v.includes('planned') ? 'is-planned' : ''}`}>{v}</span>
}

function PlanNotice({ plan, onClose }) {
  const ref = useRef(null)
  useEffect(() => {
    document.documentElement.classList.add('lp-locked')
    const prev = document.activeElement
    ref.current?.querySelector('button')?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'Tab' && ref.current) {
        const nodes = [...ref.current.querySelectorAll('a[href], button')]
        const [a, b] = [nodes[0], nodes[nodes.length - 1]]
        if (e.shiftKey && document.activeElement === a) { e.preventDefault(); b.focus() }
        else if (!e.shiftKey && document.activeElement === b) { e.preventDefault(); a.focus() }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.documentElement.classList.remove('lp-locked')
      prev?.focus?.()
    }
  }, [onClose])
  return (
    <div className="lp-modal" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} className="lp-modal__panel" role="dialog" aria-modal="true" aria-labelledby="plan-notice-title">
        <button type="button" className="lp-modal__x" onClick={onClose} aria-label="Close"><Icon name="close" /></button>
        <span className="lp-eyebrow">{plan.name} plan · {plan.state.toLowerCase()}</span>
        <h3 id="plan-notice-title">{plan.id === 'pro' ? 'The waitlist isn’t open yet.' : 'The Team plan is planned, not built.'}</h3>
        <p>
          This is a demonstration interaction. There is no waitlist backend, so <b>no form is shown and no information is collected or stored</b>.
          {plan.id === 'team' ? ' Shared workspaces, collaborative review and admin controls do not exist in this build.' : ' Pro features listed on this page are proposals.'}
        </p>
        <ul className="lp-modal__list">
          {plan.features.map((f) => <li key={f}><span className="lp-tag lp-tag--planned">Planned</span> {f}</li>)}
        </ul>
        <div className="lp-modal__actions">
          <a href={REPO_URL} target="_blank" rel="noreferrer" className="lp-btn lp-btn--ghost">
            Follow the repository <Icon name="external" />
          </a>
          <a href="/app" className="lp-btn lp-btn--primary">Start Free instead <Icon name="arrowRight" /></a>
        </div>
      </div>
    </div>
  )
}

export default function Pricing() {
  const [notice, setNotice] = useState(null)
  return (
    <section id="pricing" className="lp-section" aria-labelledby="pricing-title">
      <div className="lp-shell">
        <div className="lp-section__head lp-section__head--center">
          <Reveal><span className="lp-eyebrow">Pricing</span></Reveal>
          <SplitLines lines={['Free to start.', 'Honest about what’s next.']} className="lp-h2" />
          <span id="pricing-title" className="sr-only">Pricing</span>
          <Reveal delay={150}>
            <p className="lp-section__lead">
              Proposed prices for product planning, subject to change. No payments are taken, and no plan includes unlimited hosted AI inference.
            </p>
          </Reveal>
        </div>

        <ul className="lp-plans">
          {PLANS.map((p, i) => (
            <Reveal as="li" key={p.id} delay={i * 110} y={40}>
              <article className={`lp-plan ${p.id === 'free' ? 'is-featured' : 'is-soon'}`}>
                <div className="lp-plan__head">
                  <h3>{p.name}</h3>
                  <span className={`lp-tag ${p.id === 'free' ? 'lp-tag--procedural' : 'lp-tag--planned'}`}>{p.state}</span>
                </div>
                <div className="lp-plan__price">
                  <span>{p.price}</span><em>{p.period}</em>
                </div>
                <p className="lp-plan__blurb">{p.blurb}</p>
                <ul className="lp-plan__list">
                  {p.features.map((f) => (
                    <li key={f}>
                      {p.id === 'free' ? <Icon name="check" strokeWidth={2} /> : <span className="lp-plan__planned" aria-hidden="true" />}
                      <span>{f}{p.id !== 'free' && <span className="sr-only"> (planned)</span>}</span>
                    </li>
                  ))}
                </ul>
                {p.id === 'free' ? (
                  <a href="/app" className="lp-btn lp-btn--primary lp-btn--block">{p.cta} <Icon name="arrowRight" /></a>
                ) : (
                  <button type="button" className="lp-btn lp-btn--ghost lp-btn--block" onClick={() => setNotice(p)}>{p.cta}</button>
                )}
              </article>
            </Reveal>
          ))}
        </ul>

        <Reveal y={30} className="lp-cmp">
          <h3 className="lp-cmp__title">Feature comparison</h3>
          <div className="lp-cmp__scroll">
            <table>
              <caption className="sr-only">Feature availability by plan. Only implemented features show a checkmark.</caption>
              <thead>
                <tr><th scope="col">Feature</th><th scope="col">Status today</th><th scope="col">Free</th><th scope="col">Pro</th><th scope="col">Team</th></tr>
              </thead>
              <tbody>
                {ROWS.map(([f, st, cells]) => (
                  <tr key={f}>
                    <th scope="row">{f}</th>
                    <td><span className={`lp-cmp__status ${st.startsWith('Not') ? 'is-no' : st.startsWith('Optional') ? 'is-opt' : 'is-yes'}`}>{st}</span></td>
                    {cells.map((c, i) => <td key={i}><Cell v={c} /></td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="lp-cmp__foot">
            Hosted AI support exists as an optional backend provider that you configure with your own key. You pay the provider directly, and it has been tested against a mocked API only.
          </p>
        </Reveal>
      </div>
      {notice && <PlanNotice plan={notice} onClose={() => setNotice(null)} />}
    </section>
  )
}
