import { Faq, FinalCta, Footer } from './Closing'
import EditorShowcase from './EditorShowcase'
import { EngineProvider } from './engine'
import Hero from './Hero'
import LandingNav from './LandingNav'
import LiveDemo from './LiveDemo'
import { IntroContext } from './motion'
import Pricing from './Pricing'
import { Band, Features, Statement, Workflow } from './Sections'
import { Capabilities, Privacy } from './Trust'
import './landing.css'

export default function LandingPage() {
  return (
    <EngineProvider>
      <IntroContext.Provider value>
        <div className="lp">
          <a href="#main" className="lp-skip">Skip to content</a>
          <LandingNav />
          <main id="main">
            <Hero />
            <Statement />
            <Band />
            <LiveDemo />
            <Features />
            <Workflow />
            <EditorShowcase />
            <Privacy />
            <Capabilities />
            <Pricing />
            <Faq />
            <FinalCta />
          </main>
          <Footer />
        </div>
      </IntroContext.Provider>
    </EngineProvider>
  )
}
