import { useEffect, useState } from 'react'
import { api, assetUrl } from '../api/client'
import { LogoMark } from '../components/brand/Logo'
import EmptyState from '../components/ui/EmptyState'
import Icon from '../components/ui/Icon'
import { formatDateTime, profileSummary, relativeTime, safeStorage } from '../lib/format'
import { navigate } from '../lib/router'
import { useApp } from '../state/AppContext'

const ACTIVITY_ICON = { created: 'plus', revision: 'layers', updated: 'edit', deleted: 'trash', exported: 'download' }

export default function Workspace() {
  const { catalog, providers } = useApp()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [draft] = useState(() => safeStorage.get('revelio.draft'))

  useEffect(() => {
    let cancelled = false
    Promise.all([api.stats(), api.listSketches(), api.activity(12)])
      .then(([stats, list, act]) => !cancelled && setData({ stats, sketches: list.sketches, activity: act.activity }))
      .catch((err) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [])

  const draftSummary = draft?.profile && catalog ? profileSummary(draft.profile, catalog) : null
  const hasDraft = Boolean(draft && !draft.sketchId && (draftSummary?.known || draft.description?.trim()))
  const drafts = data?.sketches.filter((s) => s.status === 'draft').slice(0, 4) || []

  return (
    <div className="workspace">
      <section className="hero panel panel--corners reveal">
        <div className="hero__grid" aria-hidden="true" />
        <div className="hero__text">
          <span className="label label--cyan">Revelio · Forensic composite workspace</span>
          <h2 className="hero__title">From witness description<br />to forensic sketch.</h2>
          <p className="hero__lead">
            Turn a verbal description into an editable facial profile and a monochrome composite. It runs entirely on this
            machine, with optional AI providers kept clearly separate.
          </p>
          <div className="hero__actions">
            <button type="button" className="btn btn--primary btn--lg" onClick={() => navigate('new', { fresh: Date.now().toString(36) })}>
              <Icon name="newSketch" /> Create new sketch
            </button>
            {hasDraft && (
              <a className="btn btn--lg" href="#/new"><Icon name="history" /> Resume unsaved draft</a>
            )}
          </div>
          <p className="hero__disclaimer"><Icon name="shield" /> Composites assist investigations. They are not proof of identity and never identify a person automatically.</p>
        </div>
        <div className="hero__visual" aria-hidden="true">
          <div className="hero__reticle">
            <LogoMark size={120} animated />
            <span className="hero__ring" />
            <span className="hero__ring hero__ring--2" />
          </div>
          <ul className="hero__flow mono">
            <li><span>01</span> Witness description</li>
            <li><span>02</span> Structured trait profile</li>
            <li><span>03</span> Procedural composite</li>
            <li><span>04</span> Refine · compare · export</li>
          </ul>
        </div>
      </section>

      {error && <div className="alert alert--error"><Icon name="error" /><span>{error}</span></div>}

      <section className="stats stagger" aria-label="Local records">
        {[
          ['Saved sketches', data?.stats.sketches, 'library'],
          ['Drafts in progress', data?.stats.drafts, 'edit'],
          ['Revisions recorded', data?.stats.revisions, 'layers'],
        ].map(([label, value, icon]) => (
          <div key={label} className="stat panel">
            <Icon name={icon} />
            <span className="label">{label}</span>
            {data ? <span className="stat__value mono">{String(value).padStart(2, '0')}</span> : <span className="skeleton" style={{ height: 30, width: 60 }} />}
          </div>
        ))}
        <div className="stat panel">
          <Icon name="cpu" />
          <span className="label">Last-used generation mode</span>
          {data ? (
            <span className="stat__text">{data.stats.last_method || <span className="faint">None yet</span>}</span>
          ) : <span className="skeleton" style={{ height: 20, width: 140 }} />}
          {data?.stats.last_generated_at && <span className="faint mono stat__sub">{relativeTime(data.stats.last_generated_at)}</span>}
        </div>
      </section>

      <div className="workspace__grid">
        <section className="panel" aria-labelledby="recent-title">
          <div className="panel__head">
            <h2 id="recent-title" className="panel__title section-title">Recent sketches</h2>
            <a className="btn btn--ghost btn--sm" href="#/library">Open library <Icon name="arrowRight" /></a>
          </div>
          <div className="panel__body">
            {!data ? (
              <div className="recent">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 210 }} />)}</div>
            ) : data.sketches.length === 0 ? (
              <EmptyState icon="library" title="No sketches saved yet"
                action={<button type="button" className="btn btn--primary" onClick={() => navigate('new', { fresh: Date.now().toString(36) })}><Icon name="plus" /> Create the first sketch</button>}>
                Saved composites, their revisions and exports will appear here. Everything is stored locally on this machine.
              </EmptyState>
            ) : (
              <div className="recent stagger">
                {data.sketches.slice(0, 6).map((s) => (
                  <a key={s.id} className="sketch-card" href={`#/new?sketch=${encodeURIComponent(s.id)}`}>
                    <div className="sketch-card__img">
                      {s.thumbnail_url && <img src={assetUrl(s.thumbnail_url)} alt={`Composite ${s.id}`} loading="lazy" />}
                      <span className={`tag ${s.is_ai ? 'tag--ai' : 'tag--procedural'}`}>{s.is_ai ? 'AI' : 'Procedural'}</span>
                    </div>
                    <div className="sketch-card__body">
                      <strong>{s.title}</strong>
                      <span className="mono faint">{s.id} · R{s.rev_number}</span>
                      <span className="faint">{relativeTime(s.updated_at)}</span>
                    </div>
                  </a>
                ))}
              </div>
            )}
          </div>
        </section>

        <div className="workspace__side">
          <section className="panel" aria-labelledby="unfinished-title">
            <div className="panel__head">
              <h2 id="unfinished-title" className="panel__title section-title">Unfinished work</h2>
            </div>
            <div className="panel__body">
              {hasDraft && (
                <a className="draft-row is-local" href="#/new">
                  <Icon name="history" />
                  <span>
                    <strong>{draft.title || 'Unsaved draft'}</strong>
                    <span className="faint mono">This browser · {draftSummary?.known || 0} traits · {formatDateTime(draft.savedAt)}</span>
                  </span>
                  <Icon name="chevronRight" />
                </a>
              )}
              {drafts.map((s) => (
                <a key={s.id} className="draft-row" href={`#/new?sketch=${encodeURIComponent(s.id)}`}>
                  <Icon name="edit" />
                  <span>
                    <strong>{s.title}</strong>
                    <span className="faint mono">{s.id} · {s.revision_count} rev · draft</span>
                  </span>
                  <Icon name="chevronRight" />
                </a>
              ))}
              {data && !hasDraft && drafts.length === 0 && <p className="faint">No unfinished work. Sketches stay drafts until you mark them final in the library.</p>}
            </div>
          </section>

          <section className="panel" aria-labelledby="activity-title">
            <div className="panel__head">
              <h2 id="activity-title" className="panel__title section-title">Recent activity</h2>
              <span className="label">Local log</span>
            </div>
            <div className="panel__body">
              {!data ? (
                <div className="skeleton" style={{ height: 120 }} />
              ) : data.activity.length === 0 ? (
                <p className="faint">No activity recorded yet.</p>
              ) : (
                <ol className="timeline">
                  {data.activity.map((a) => (
                    <li key={a.id} className={`timeline__item is-${a.kind}`}>
                      <span className="timeline__node"><Icon name={ACTIVITY_ICON[a.kind] || 'dot'} /></span>
                      <span className="timeline__msg">{a.message}</span>
                      <span className="timeline__time mono faint">{relativeTime(a.created_at)}</span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </section>

          <section className="panel" aria-labelledby="providers-title">
            <div className="panel__head">
              <h2 id="providers-title" className="panel__title section-title">Generation providers</h2>
              <a className="btn btn--ghost btn--sm" href="#/settings">Details</a>
            </div>
            <ul className="panel__body provider-mini">
              {['offline', 'local', 'hosted'].map((id) => (
                <li key={id}>
                  <span className={`dot ${providers[id]?.available ? 'dot--ok' : 'dot--idle'}`} />
                  <span>{providers[id]?.label}</span>
                  <span className={`tag ${providers[id]?.runs_locally ? 'tag--local' : 'tag--remote'}`}>{providers[id]?.runs_locally ? 'Local' : 'Remote'}</span>
                  <span className="mono faint">{providers[id]?.available ? 'READY' : (providers[id]?.state || '').replace('_', ' ').toUpperCase()}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  )
}
