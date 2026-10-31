import { useCallback, useEffect, useState } from 'react'
import { api, assetUrl } from '../api/client'
import EmptyState from '../components/ui/EmptyState'
import Icon from '../components/ui/Icon'
import { ConfirmModal, Modal } from '../components/ui/Modal'
import { formatDateTime, relativeTime } from '../lib/format'
import { navigate } from '../lib/router'
import { useApp } from '../state/AppContext'

function HistoryModal({ id, onClose }) {
  const [sketch, setSketch] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    api.getSketch(id).then(setSketch).catch((e) => setError(e.message))
  }, [id])
  return (
    <Modal title={`Revision history · ${id}`} onClose={onClose} wide>
      {error && <div className="alert alert--error"><Icon name="error" /><span>{error}</span></div>}
      {!sketch ? <div className="skeleton" style={{ height: 200 }} /> : (
        <ol className="history">
          {[...sketch.revisions].reverse().map((r) => (
            <li key={r.number} className="history__item">
              <img src={assetUrl(r.image_url)} alt={`Revision ${r.number}`} loading="lazy" />
              <div className="history__body">
                <div className="history__top">
                  <span className="mono">R{r.number}</span>
                  <span className={`tag ${r.is_ai ? 'tag--ai' : 'tag--procedural'}`}>{r.is_ai ? 'AI-generated' : 'Procedural'}</span>
                  <span className="faint mono">{formatDateTime(r.created_at)}</span>
                </div>
                <p className="muted">{r.change_note || 'No note'}</p>
                <span className="faint">{r.method_label}</span>
                <div className="history__actions">
                  <a className="btn btn--sm" href={`#/new?sketch=${encodeURIComponent(id)}&rev=${r.number}`}><Icon name="edit" /> Continue from here</a>
                  <a className="btn btn--ghost btn--sm" href={api.pngDownloadUrl(id, r.number)}><Icon name="download" /> PNG</a>
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Modal>
  )
}

export default function Library() {
  const { notify } = useApp()
  const [query, setQuery] = useState('')
  const [items, setItems] = useState(null)
  const [removing, setRemoving] = useState(null)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [historyFor, setHistoryFor] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async (q) => {
    try {
      const r = await api.listSketches(q)
      setItems(r.sketches)
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    const t = setTimeout(() => load(query.trim()), query ? 220 : 0)
    return () => clearTimeout(t)
  }, [query, load])

  const rename = async (s, title) => {
    setEditing(null)
    if (!title.trim() || title.trim() === s.title) return
    try {
      await api.updateSketch(s.id, { title: title.trim() })
      notify({ kind: 'ok', title: 'Sketch renamed', message: `${s.id} → “${title.trim()}”` })
      load(query.trim())
    } catch (err) {
      notify({ kind: 'error', title: 'Rename failed', message: err.message })
    }
  }

  const toggleStatus = async (s) => {
    try {
      await api.updateSketch(s.id, { status: s.status === 'draft' ? 'final' : 'draft' })
      load(query.trim())
    } catch (err) {
      notify({ kind: 'error', title: 'Update failed', message: err.message })
    }
  }

  const remove = async () => {
    setBusy(true)
    try {
      await api.deleteSketch(confirm.id)
      notify({ kind: 'ok', title: `${confirm.id} deleted`, message: 'The sketch, its revisions and its image files were removed.' })
      setRemoving(confirm.id)
      setConfirm(null)
      // Let the card fade out before the list reloads without it.
      await new Promise((resolve) => setTimeout(resolve, document.documentElement.classList.contains('reduce-motion') ? 0 : 220))
      setRemoving(null)
      load(query.trim())
    } catch (err) {
      notify({ kind: 'error', title: 'Delete failed', message: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="library reveal">
      <div className="toolbar panel">
        <label className="search">
          <Icon name="search" />
          <span className="sr-only">Search sketches</span>
          <input className="input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by title, sketch ID or description" />
        </label>
        <span className="mono faint">{items ? `${items.length} record${items.length === 1 ? '' : 's'}` : '—'}</span>
        <button type="button" className="btn btn--primary" onClick={() => navigate('new', { fresh: Date.now().toString(36) })}><Icon name="plus" /> New sketch</button>
      </div>

      {error && <div className="alert alert--error"><Icon name="error" /><span>{error}</span></div>}

      {!items ? (
        <div className="library__grid">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 360 }} />)}</div>
      ) : items.length === 0 ? (
        <EmptyState icon="library" title={query ? 'No sketches match this search' : 'The library is empty'}
          action={!query && <button type="button" className="btn btn--primary" onClick={() => navigate('new', { fresh: Date.now().toString(36) })}><Icon name="plus" /> Create a sketch</button>}>
          {query ? 'Try another title, sketch ID or word from the description.' : 'Saved composites are stored locally with their full revision history.'}
        </EmptyState>
      ) : (
        <div className="library__grid stagger">
          {items.map((s, i) => (
            <article key={s.id} className={`lib-card panel lib-card--enter ${removing === s.id ? 'is-removing' : ''}`} style={{ '--i': Math.min(i, 10) }}>
              <a className="lib-card__img" href={`#/new?sketch=${encodeURIComponent(s.id)}`} aria-label={`Open ${s.title}`}>
                {s.thumbnail_url && <img src={assetUrl(s.thumbnail_url)} alt="" loading="lazy" />}
                <span className={`tag ${s.is_ai ? 'tag--ai' : 'tag--procedural'}`}>{s.is_ai ? 'AI-generated' : 'Procedural'}</span>
              </a>
              <div className="lib-card__body">
                {editing === s.id ? (
                  <input className="input input--sm" defaultValue={s.title} autoFocus maxLength={120} aria-label="New title"
                    onBlur={(e) => rename(s, e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') setEditing(null) }} />
                ) : (
                  <h3 className="lib-card__title">
                    <span>{s.title}</span>
                    <button type="button" className="btn btn--ghost btn--icon btn--sm" onClick={() => setEditing(s.id)} aria-label={`Rename ${s.title}`}><Icon name="edit" /></button>
                  </h3>
                )}
                <div className="lib-card__meta">
                  <span className="mono">{s.id}</span>
                  <button type="button" className={`chip ${s.status === 'final' ? 'chip--green' : 'chip--amber'}`} onClick={() => toggleStatus(s)} title="Toggle draft / final">
                    {s.status === 'final' ? 'Final' : 'Draft'}
                  </button>
                </div>
                <div className="lib-card__meta faint">
                  <span className="mono">{s.revision_count} rev</span>
                  <span>Updated {relativeTime(s.updated_at)}</span>
                </div>
                <p className="lib-card__method faint">{s.method_label}</p>
                <div className="lib-card__actions">
                  <a className="btn btn--sm" href={`#/new?sketch=${encodeURIComponent(s.id)}`}><Icon name="edit" /> Open</a>
                  <button type="button" className="btn btn--ghost btn--sm" onClick={() => setHistoryFor(s.id)}><Icon name="history" /> History</button>
                  <a className="btn btn--ghost btn--sm" href={`#/compare?sketch=${encodeURIComponent(s.id)}`}><Icon name="compare" /></a>
                </div>
                <div className="lib-card__export">
                  <span className="label">Export</span>
                  <a className="btn btn--ghost btn--sm" href={api.pngDownloadUrl(s.id, s.rev_number)}><Icon name="image" /> PNG</a>
                  <a className="btn btn--ghost btn--sm" href={api.exportJsonUrl(s.id)}><Icon name="json" /> JSON</a>
                  <a className="btn btn--ghost btn--sm" href={api.reportUrl(s.id)} target="_blank" rel="noreferrer"><Icon name="printer" /> Report</a>
                  <button type="button" className="btn btn--ghost btn--icon btn--sm lib-card__del" onClick={() => setConfirm(s)} aria-label={`Delete ${s.title}`}><Icon name="trash" /></button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      {confirm && (
        <ConfirmModal
          title="Delete sketch?"
          danger
          busy={busy}
          confirmLabel="Delete permanently"
          message={<>This permanently deletes <span className="mono">{confirm.id}</span> “{confirm.title}”, all {confirm.revision_count} revision(s) and their image files from this machine. This cannot be undone.</>}
          onConfirm={remove}
          onClose={() => setConfirm(null)}
        />
      )}
      {historyFor && <HistoryModal id={historyFor} onClose={() => setHistoryFor(null)} />}
    </div>
  )
}
