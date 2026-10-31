import { BrandLogo } from '../components/brand/Logo'
import ThemeToggle from '../components/ui/ThemeToggle'
import './landing.css'

// Landing page for the PRD "Multi-Tenant Aggregation Layer" (see ps_documentation.md).
// Targets are shown as PRD targets only; this page never claims a target is met.

const QUESTIONS = [
  { q: 'How many orders were received today?', fr: 'FR-1', kind: 'Counts and totals' },
  { q: 'What are the sales trends this month?', fr: 'FR-2', kind: 'Trends over time' },
  { q: 'What are the top 10 products this week?', fr: 'FR-3', kind: 'Top-N lists' },
  { q: 'How many orders are placed, shipped or cancelled?', fr: 'FR-4', kind: 'Breakdown by category' },
]

const PROBLEMS = [
  { t: 'Slow dashboards', d: 'Counting and ranking millions of orders on every page view takes seconds, not milliseconds.' },
  { t: 'A slower store', d: 'Heavy analytical scans compete with checkout for CPU, memory and I/O on the main database.' },
  { t: 'Stale numbers', d: 'Nightly batch jobs leave dashboards up to a day behind, and late cancellations are missed.' },
  { t: 'Leaky tenants', d: 'Shared tables, summaries and caches are all places where one store could see another\'s data.' },
]

const FRS = [
  ['FR-1', 'Counts and totals for a time range', 'Orders and total sales over the last 7 days.'],
  ['FR-2', 'Trends over time', 'Orders per day for 30 days, or hourly trends.'],
  ['FR-3', 'Top-N lists', 'Top 10 products by sales this week.'],
  ['FR-4', 'Breakdown by category', 'Orders grouped by status: placed, shipped, cancelled.'],
  ['FR-5', 'Tenant filter on every query', 'Tenant A never sees Tenant B\'s analytics.'],
  ['FR-6', 'New data appears in results', 'New and updated orders show up within minutes.'],
  ['FR-7', 'Simple analytics API', 'REST endpoints that return dashboard numbers.'],
]

const FLOW = [
  ['Store app', 'Orders are inserted, updated and cancelled as usual.'],
  ['PostgreSQL', 'Source rows carry tenant_id. Each shard is an independent database.'],
  ['Change capture', 'pg_trickle trigger CDC records every change in the same transaction.'],
  ['Stream tables', 'Incremental (DIFFERENTIAL) per-tenant summaries by day, hour, product, category and status.'],
  ['Analytics API', 'Routes each tenant to its shard; reads run under row-level security; exact partial-day edges.'],
  ['Dashboard', 'Sales, trends, Top-10, breakdowns, freshness and live updates.'],
]

const SCORE = [
  ['Query speed', 'Under 1 second', 'Under 200 ms'],
  ['Freshness', 'Under 5 minutes', 'Under 30 seconds'],
  ['Database safety', 'Less than 25% slower', 'Less than 10% slower'],
  ['Correctness', 'Matches on most queries', 'Matches on all queries'],
  ['Growth', 'Less than 5x slower at 10M', 'Less than 2x slower at 10M'],
]

const BONUS = [
  ['B-1', 'Shows how fresh the data is', 'Every response + dashboard badge', true],
  ['B-2', 'Rebuild all numbers from scratch', 'Operator CLI, oracle-verified', true],
  ['B-3', 'Limit heavy queries per tenant', 'Per-tenant limit (429)', true],
  ['B-4', 'New metric from a config file', 'Not built yet', false],
  ['B-5', 'Monitoring page: query time and data lag', 'Engine and Shards pages', true],
]

export default function LandingPage() {
  return (
    <div className="ax-land">
      <header className="ax-land__nav">
        <a href="/" aria-label="AggregateX home"><BrandLogo height={32} /></a>
        <nav aria-label="Sections">
          <a href="#problem">Problem</a>
          <a href="#requirements">Requirements</a>
          <a href="#architecture">How it works</a>
          <a href="#targets">Targets</a>
        </nav>
        <div className="ax-land__nav-right">
          <ThemeToggle className="btn btn--ghost btn--icon" />
          <a className="btn btn--primary btn--sm" href="/app">Open dashboard</a>
        </div>
      </header>

      <main>
        <section className="ax-land__hero">
          <div>
            <span className="label label--cyan">Multi-tenant aggregation layer</span>
            <h1>Fast, fresh, tenant-isolated analytics for every store.</h1>
            <p className="ax-land__lead">
              An online-store platform hosts many stores, and every owner wants dashboards. AggregateX sits between the main
              database and those dashboards. It keeps per-tenant summaries current as orders change, so a dashboard reads a few
              summary rows instead of scanning millions of orders.
            </p>
            <div className="ax-land__cta">
              <a className="btn btn--primary" href="/app">Open the dashboard</a>
              <a className="btn btn--ghost" href="#architecture">How it works</a>
            </div>
          </div>
          <ul className="ax-land__questions" aria-label="Questions store owners ask">
            {QUESTIONS.map((x) => (
              <li key={x.fr} className="panel">
                <span className="mono ax-land__fr">{x.fr}</span>
                <strong>{x.q}</strong>
                <span className="faint">{x.kind}</span>
              </li>
            ))}
          </ul>
        </section>

        <section id="problem" className="ax-land__section">
          <h2>The problem</h2>
          <p className="ax-land__intro">Simple queries get expensive once a platform holds millions of orders across many tenants.</p>
          <div className="ax-land__grid4">
            {PROBLEMS.map((p) => (
              <div key={p.t} className="panel ax-land__card"><h3>{p.t}</h3><p className="muted">{p.d}</p></div>
            ))}
          </div>
        </section>

        <section id="requirements" className="ax-land__section">
          <h2>What it must do</h2>
          <p className="ax-land__intro">The seven mandatory functional requirements from the PRD.</p>
          <div className="ax-land__grid3">
            {FRS.map(([id, t, d]) => (
              <div key={id} className="panel ax-land__card">
                <span className="mono ax-land__fr">{id}</span><h3>{t}</h3><p className="muted">{d}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="architecture" className="ax-land__section">
          <h2>How it works</h2>
          <p className="ax-land__intro">From an order being written to a number on the dashboard.</p>
          <ol className="ax-land__flow">
            {FLOW.map(([t, d], i) => (
              <li key={t} className="panel">
                <span className="mono ax-land__step">{String(i + 1).padStart(2, '0')}</span>
                <h3>{t}</h3><p className="muted">{d}</p>
              </li>
            ))}
          </ol>
          <p className="faint ax-land__note">
            Sharded mode: tenants are assigned to two independent database shards by a versioned directory. If a shard is
            unreachable, its tenants get an explicit 503, other shards keep working, and global totals are marked partial.
            There is no automatic failover.
          </p>
        </section>

        <section id="targets" className="ax-land__section">
          <h2>Scorecard targets</h2>
          <p className="ax-land__intro">
            From the PRD, tested at 1 million records / 10 tenants and 10 million records / 100 tenants, with some tenants much
            larger than others. <strong>These are targets, not claims.</strong> Measured results and failures are recorded in the
            repository.
          </p>
          <div className="panel ax-land__tablewrap">
            <table className="ax-land__table">
              <thead><tr><th>Metric</th><th>Good</th><th>Great</th></tr></thead>
              <tbody>{SCORE.map(([m, g, gr]) => <tr key={m}><td>{m}</td><td>{g}</td><td>{gr}</td></tr>)}</tbody>
            </table>
          </div>
          <h3 className="ax-land__h3">Bonus</h3>
          <ul className="ax-land__bonus">
            {BONUS.map(([id, t, s, done]) => (
              <li key={id}>
                <span className="mono ax-land__fr">{id}</span>
                <span>{t}</span>
                <span className={`ax-land__status ${done ? 'is-done' : ''}`}>{s}</span>
              </li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="ax-land__foot">
        <BrandLogo height={22} />
        <span className="faint">
          Aggregation engine: <a href="https://github.com/trickle-labs/pg-trickle">pg_trickle</a> (Apache-2.0, trickle-labs).
          Demo data is representative, not organiser data.
        </span>
      </footer>
    </div>
  )
}
