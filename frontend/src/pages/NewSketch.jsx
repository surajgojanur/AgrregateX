import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { api, assetUrl } from '../api/client'
import AdjustPanel from '../components/sketch/AdjustPanel'
import DescriptionPanel from '../components/sketch/DescriptionPanel'
import ModeSelector from '../components/sketch/ModeSelector'
import Pipeline from '../components/sketch/Pipeline'
import RefinePanel from '../components/sketch/RefinePanel'
import ReferenceUpload from '../components/sketch/ReferenceUpload'
import RenderNotes from '../components/sketch/RenderNotes'
import SketchViewer from '../components/sketch/SketchViewer'
import TraitPanel from '../components/sketch/TraitPanel'
import EmptyState from '../components/ui/EmptyState'
import Icon from '../components/ui/Icon'
import { downloadBlob, emptyProfile, formatDateTime, profileSummary, safeStorage } from '../lib/format'
import { navigate } from '../lib/router'
import { useApp } from '../state/AppContext'

const DRAFT_KEY = 'revelio.draft'

// ---- profile history (undo / redo) ---------------------------------------
function historyReducer(state, action) {
  switch (action.type) {
    case 'load':
      return { past: [], present: action.profile, future: [], key: null, at: 0 }
    case 'replace':
      return { ...state, present: action.profile }
    case 'set': {
      const coalesce = action.key && action.key === state.key && action.at - state.at < 900
      return {
        past: coalesce ? state.past : [...state.past, state.present].slice(-80),
        present: action.profile, future: [], key: action.key, at: action.at,
      }
    }
    case 'undo':
      if (!state.past.length) return state
      return { past: state.past.slice(0, -1), present: state.past[state.past.length - 1], future: [state.present, ...state.future], key: null, at: 0 }
    case 'redo':
      if (!state.future.length) return state
      return { past: [...state.past, state.present], present: state.future[0], future: state.future.slice(1), key: null, at: 0 }
    default:
      return state
  }
}

const hasContent = (p) => Boolean(
  Object.values(p.traits || {}).some((t) => t?.value || t?.alternatives?.length) || p.marks?.length ||
  Object.keys(p.adjustments || {}).length || p.observations?.trim(),
)

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)

function Elapsed({ since }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(id)
  }, [])
  return <span className="mono">{((now - since) / 1000).toFixed(1)}s</span>
}

export default function NewSketch({ params }) {
  const { catalog, providers, notify, setActiveCase } = useApp()
  const [restored] = useState(() => (!params.sketch && !params.fresh ? safeStorage.get(DRAFT_KEY) : null))
  const [title, setTitle] = useState(restored?.title || '')
  const [description, setDescription] = useState(restored?.description || '')
  const [reveal, setReveal] = useState(0) // bumps after each extraction so traits re-reveal
  const [mode, setMode] = useState(restored?.mode && restored.mode !== 'local' ? restored.mode : 'offline')
  const [hist, dispatch] = useReducer(historyReducer, null, () => ({ past: [], present: restored?.profile || emptyProfile(), future: [], key: null, at: 0 }))
  const profile = hist.present
  const [baseline, setBaseline] = useState(() => restored?.baseline || restored?.profile || emptyProfile())
  const [meta, setMeta] = useState(null)
  const [sketch, setSketch] = useState(null)
  const [viewingRev, setViewingRev] = useState(null)
  const [loadingSketch, setLoadingSketch] = useState(Boolean(params.sketch))
  const [loadError, setLoadError] = useState(null)
  const [preview, setPreview] = useState({ url: null, notes: [], loading: false, error: null })
  const [gen, setGen] = useState(null)
  const [genError, setGenError] = useState(null)
  const [tab, setTab] = useState('profile')
  const [reference, setReference] = useState(null)
  const [changeNote, setChangeNote] = useState('')
  const [downloadBusy, setDownloadBusy] = useState(false)
  const [showRestored, setShowRestored] = useState(Boolean(restored && hasContent(restored.profile || {})))
  const previewUrl = useRef(null)

  // Hosted mode may have been disabled since the draft was saved.
  const effectiveMode = providers[mode]?.available ? mode : 'offline'

  const setProfile = useCallback((next, key) => dispatch({ type: 'set', profile: next, key, at: Date.now() }), [])

  // ---- load a saved sketch ----------------------------------------------
  useEffect(() => {
    if (!params.sketch) return undefined
    let cancelled = false
    api.getSketch(params.sketch)
      .then((s) => {
        if (cancelled) return
        const n = Number(params.rev) || s.current?.number
        const rev = s.revisions.find((r) => r.number === n) || s.current
        setSketch(s)
        setTitle(s.title)
        setDescription(s.description || '')
        setViewingRev(rev?.number ?? null)
        if (rev) {
          dispatch({ type: 'load', profile: rev.profile })
          setBaseline(s.revisions[0]?.profile || rev.profile)
          if (rev.method === 'hosted_gemini' && providers.hosted?.available) setMode('hosted')
        }
        setLoadingSketch(false)
      })
      .catch((err) => {
        if (cancelled) return
        setLoadError(err.message)
        setLoadingSketch(false)
      })
    return () => {
      cancelled = true
    }
  }, [params.sketch, params.rev, providers.hosted?.available])

  // ---- live procedural preview (debounced, cancellable) -------------------
  const caption = sketch?.id || 'DRAFT'
  const renderable = hasContent(profile) || Boolean(sketch)
  useEffect(() => {
    if (!renderable) return undefined
    const ctrl = new AbortController()
    const timer = setTimeout(async () => {
      setPreview((p) => ({ ...p, loading: true, error: null }))
      try {
        const r = await api.render(profile, caption, ctrl.signal)
        const url = URL.createObjectURL(new Blob([r.svg], { type: 'image/svg+xml' }))
        if (previewUrl.current) URL.revokeObjectURL(previewUrl.current)
        previewUrl.current = url
        setPreview({ url, notes: r.notes, loading: false, error: null })
      } catch (err) {
        if (err.name !== 'AbortError') setPreview((p) => ({ ...p, loading: false, error: err.message }))
      }
    }, 140)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
  }, [profile, caption, renderable])

  useEffect(() => () => previewUrl.current && URL.revokeObjectURL(previewUrl.current), [])

  // ---- draft autosave (this browser only) ----------------------------------
  useEffect(() => {
    if (loadingSketch) return undefined
    const t = setTimeout(() => {
      if (hasContent(profile) || description.trim() || sketch) {
        safeStorage.set(DRAFT_KEY, { title, description, profile, baseline, mode, sketchId: sketch?.id || null, savedAt: new Date().toISOString() })
      }
    }, 500)
    return () => clearTimeout(t)
  }, [title, description, profile, baseline, mode, sketch, loadingSketch])

  const savedRev = sketch?.revisions.find((r) => r.number === viewingRev) || null
  const dirty = !savedRev || !same(savedRev.profile, profile)

  useEffect(() => {
    setActiveCase(sketch ? { id: sketch.id, title: sketch.title, revision: viewingRev } : hasContent(profile) ? { draft: true } : null)
  }, [sketch, viewingRev, profile, setActiveCase])
  useEffect(() => () => setActiveCase(null), [setActiveCase])

  // ---- keyboard shortcuts: ⌘Z / ⇧⌘Z ----------------------------------------
  useEffect(() => {
    const onKey = (e) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== 'z') return
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return
      e.preventDefault()
      dispatch({ type: e.shiftKey ? 'redo' : 'undo' })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // ---- input handlers -------------------------------------------------------
  const onExtracted = (result) => {
    const next = { ...result.profile, adjustments: profile.adjustments || {}, observations: profile.observations || '' }
    setProfile(next, 'extract')
    setReveal((n) => n + 1)
    if (!sketch) setBaseline(next)
    setMeta(result)
    setTab('profile')
  }

  const onGuided = ({ answers, marks, observations }) => {
    const next = structuredClone(profile)
    for (const [key, value] of Object.entries(answers)) {
      if (value) next.traits[key] = { value, source: 'described', evidence: 'Guided question', certainty: 'stated', alternatives: [] }
    }
    marks.forEach((m, i) => next.marks.push({ id: `g${Date.now().toString(36)}${i}`, ...m, dx: 0, dy: 0, side_specified: true, source: 'described', evidence: 'Guided question' }))
    if (observations.trim()) next.observations = [next.observations, observations.trim()].filter(Boolean).join('\n').slice(0, 1000)
    setProfile(next, 'guided')
    setReveal((n) => n + 1)
    if (!sketch && !hasContent(baseline)) setBaseline(next)
    setTab('profile')
    notify({ kind: 'ok', title: 'Guided answers applied', message: 'Marked as “Described” in the profile.' })
  }

  const onMerged = ({ profile: merged, description: text }) => {
    const next = { ...merged, adjustments: profile.adjustments || {}, observations: profile.observations || '' }
    setProfile(next, 'merge')
    setReveal((n) => n + 1)
    setDescription(text.slice(0, 2000))
    if (!sketch) setBaseline(next)
    setTab('profile')
    notify({ kind: 'ok', title: 'Combined witness profile applied', message: 'Single-source traits are flagged in the evidence notes.' })
  }

  const onRefined = (next, changes) => {
    setProfile(next, 'refine')
    setChangeNote((n) => n || changes.map((c) => `${c.label}: ${c.to_label}`).join('; ').slice(0, 280))
  }

  // ---- save / generate ------------------------------------------------------
  const save = async (useMode) => {
    const m = useMode || effectiveMode
    setGenError(null)
    setGen({ mode: m, since: Date.now() })
    try {
      const payload = {
        profile, mode: m, note: changeNote.trim() || undefined,
        reference_image: providers[m]?.supports_reference_image && reference ? reference.dataUrl : undefined,
      }
      const s = sketch
        ? await api.addRevision(sketch.id, payload)
        : await api.generate({ ...payload, title: title.trim() || 'Untitled composite', description: description.trim() })
      setSketch(s)
      setViewingRev(s.current.number)
      dispatch({ type: 'replace', profile: s.current.profile })
      setChangeNote('')
      setShowRestored(false)
      window.history.replaceState(null, '', `#/new?sketch=${encodeURIComponent(s.id)}`)
      notify({ kind: 'ok', title: `${s.id} · revision ${s.current.number} saved`, message: s.current.method_label })
    } catch (err) {
      setGenError({ message: err.message, provider: Boolean(err.isProviderError), mode: m })
      notify({ kind: 'error', title: m === 'offline' ? 'Save failed' : `${providers[m]?.label} failed`, message: err.message, timeout: 7000 })
    } finally {
      setGen(null)
    }
  }

  const renameIfSaved = async () => {
    if (!sketch || !title.trim() || title.trim() === sketch.title) return
    try {
      const s = await api.updateSketch(sketch.id, { title: title.trim() })
      setSketch(s)
      notify({ kind: 'ok', title: 'Sketch renamed' })
    } catch (err) {
      notify({ kind: 'error', title: 'Rename failed', message: err.message })
    }
  }

  const openRevision = (rev) => {
    setViewingRev(rev.number)
    setProfile(rev.profile, `rev:${rev.number}`)
  }

  const startFresh = () => {
    safeStorage.remove(DRAFT_KEY)
    navigate('new', { fresh: Date.now().toString(36) })
  }

  const download = async () => {
    if (savedRev && !dirty) {
      const a = document.createElement('a')
      a.href = api.pngDownloadUrl(sketch.id, savedRev.number)
      a.click()
      return
    }
    setDownloadBusy(true)
    try {
      downloadBlob(await api.renderPng(profile, caption), `${sketch?.id || 'revelio-draft'}-preview.png`)
    } catch (err) {
      notify({ kind: 'error', title: 'Export failed', message: err.message })
    } finally {
      setDownloadBusy(false)
    }
  }

  // ---- derived view state -----------------------------------------------------
  const summary = profileSummary(profile, catalog)
  const showSavedAi = savedRev && !dirty && savedRev.is_ai
  const viewer = showSavedAi
    ? { src: assetUrl(savedRev.image_url), kind: 'ai', label: `Revision ${savedRev.number}`, sublabel: savedRev.method_label }
    : {
        src: renderable ? preview.url : null, kind: 'procedural',
        label: savedRev && !dirty ? `Revision ${savedRev.number}` : 'Live preview',
        sublabel: savedRev && !dirty ? 'Saved' : sketch ? 'Unsaved changes' : 'Not saved yet',
      }
  let before = null
  if (savedRev && dirty) before = { src: assetUrl(savedRev.image_url), label: `R${savedRev.number}` }
  else if (savedRev && savedRev.number > 1) {
    const prev = sketch.revisions.find((r) => r.number === savedRev.number - 1)
    if (prev) before = { src: assetUrl(prev.image_url), label: `R${prev.number}` }
  }
  const notes = showSavedAi ? savedRev.notes : preview.notes
  const aiNotice = savedRev?.is_ai
    ? 'This revision is an AI-generated image. Edits update the profile and the procedural preview immediately; the AI image only changes when you regenerate it with Hosted AI.'
    : effectiveMode === 'hosted'
      ? 'Hosted AI is selected. Sliders preview through the offline renderer; the AI image is produced only when you click Generate.'
      : null
  const provider = providers[effectiveMode]

  const steps = [
    { id: 'desc', label: 'Description', state: description.trim() || summary.known ? 'done' : 'active', detail: description.trim() ? `${description.trim().length} chars` : summary.known ? 'guided / merged' : 'awaiting input' },
    { id: 'extract', label: 'Trait profile', state: summary.known || summary.marks ? 'done' : description.trim() ? 'active' : 'pending', detail: `${summary.known} known · ${summary.unknown} unknown` },
    { id: 'review', label: 'Operator review', state: summary.conflicts ? 'warn' : summary.known ? 'done' : 'pending', detail: summary.conflicts ? `${summary.conflicts} conflict${summary.conflicts > 1 ? 's' : ''}` : summary.known ? 'no conflicts' : '—' },
    { id: 'render', label: 'Composite', state: preview.error ? 'warn' : preview.loading ? 'active' : renderable && preview.url ? 'done' : 'pending', detail: preview.error ? 'render error' : preview.loading ? 'rendering…' : renderable && preview.url ? 'procedural' : '—' },
    { id: 'save', label: 'Revision', state: gen ? 'active' : savedRev && !dirty ? 'done' : 'pending', detail: gen ? 'saving…' : savedRev ? `R${savedRev.number}${dirty ? ' · edited' : ''}` : 'unsaved' },
  ]

  if (loadingSketch) {
    return (
      <div className="page-fallback" aria-busy="true">
        <div className="skeleton" style={{ height: 40 }} />
        <div className="skeleton" style={{ height: 480 }} />
      </div>
    )
  }
  if (loadError) {
    return (
      <EmptyState icon="alert" title="This sketch could not be opened" action={<a className="btn" href="#/library">Back to library</a>}>
        {loadError}
      </EmptyState>
    )
  }

  const primaryLabel = effectiveMode === 'hosted'
    ? (sketch ? 'Regenerate with Hosted AI' : 'Generate with Hosted AI')
    : (sketch ? 'Save revision' : 'Save composite')

  return (
    <div className="studio reveal">
      {showRestored && (
        <div className="alert alert--info studio__restored">
          <Icon name="history" />
          <span>Restored your unsaved draft from this browser{restored?.savedAt ? ` (${formatDateTime(restored.savedAt)})` : ''}.</span>
          <button type="button" className="btn btn--sm" onClick={startFresh}>Start fresh</button>
          <button type="button" className="btn btn--ghost btn--icon btn--sm" onClick={() => setShowRestored(false)} aria-label="Dismiss"><Icon name="close" /></button>
        </div>
      )}

      <div className="studio__head panel">
        <div className="studio__ident">
          <label className="sr-only" htmlFor="sketch-title">Sketch title</label>
          <input id="sketch-title" className="studio__title" value={title} maxLength={120} placeholder="Untitled composite"
            onChange={(e) => setTitle(e.target.value)} onBlur={renameIfSaved} onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()} />
          <div className="studio__ids">
            <span className="mono chip">{sketch ? sketch.id : 'NOT SAVED'}</span>
            {sketch && <span className="mono faint">{sketch.revision_count} revision{sketch.revision_count > 1 ? 's' : ''} · {sketch.status}</span>}
          </div>
        </div>
        <Pipeline steps={steps} />
        <div className="studio__actions">
          <button type="button" className="btn btn--ghost btn--icon" onClick={() => dispatch({ type: 'undo' })} disabled={!hist.past.length} aria-label="Undo" title="Undo (⌘Z)"><Icon name="undo" /></button>
          <button type="button" className="btn btn--ghost btn--icon" onClick={() => dispatch({ type: 'redo' })} disabled={!hist.future.length} aria-label="Redo" title="Redo (⇧⌘Z)"><Icon name="redo" /></button>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setProfile(baseline, 'reset')} disabled={same(baseline, profile)} title="Reset to the original extracted profile">
            <Icon name="reset" /> Reset
          </button>
          <button type="button" className="btn btn--ghost btn--sm" onClick={startFresh} title="Start a new sketch"><Icon name="plus" /> New</button>
        </div>
      </div>

      <div className="studio__grid">
        <div className="studio__input">
          <DescriptionPanel description={description} onDescriptionChange={setDescription} onExtracted={onExtracted} onGuided={onGuided} onMerged={onMerged} />
          {meta && (meta.conflicts.length > 0 || meta.explicit_unknowns.length > 0 || meta.warnings.length > 0) && (
            <div className="extract-notes reveal">
              {meta.conflicts.length > 0 && (
                <div className="alert alert--warn"><Icon name="alert" /><span><strong>{meta.conflicts.length} conflicting statement{meta.conflicts.length > 1 ? 's' : ''}.</strong> Resolve in the profile panel; conflicting traits stay unknown until you choose.</span></div>
              )}
              {meta.explicit_unknowns.length > 0 && (
                <div className="alert alert--info"><Icon name="info" /><span>Witness explicitly could not recall: {meta.explicit_unknowns.map((k) => catalog.traits.find((t) => t.key === k)?.label).join(', ')}. Kept as unknown.</span></div>
              )}
              {meta.warnings.map((w) => <div key={w} className="alert alert--warn"><Icon name="alert" /><span>{w}</span></div>)}
            </div>
          )}
          <ModeSelector mode={effectiveMode} onChange={setMode} />
          <ReferenceUpload value={reference} onChange={setReference} supported={Boolean(provider?.supports_reference_image)} providerLabel={provider?.label} />
        </div>

        <div className="studio__center">
          <SketchViewer
            src={viewer.src}
            kind={viewer.kind}
            label={viewer.label}
            sublabel={viewer.sublabel}
            loading={preview.loading && !showSavedAi}
            error={!showSavedAi ? preview.error : null}
            before={before}
            onDownload={download}
            downloadBusy={downloadBusy}
            meta={[
              ['Sketch', sketch?.id || 'unsaved'],
              ['Revision', savedRev ? `R${savedRev.number}${dirty ? ' + edits' : ''}` : '—'],
              ['Method', showSavedAi ? 'hosted AI' : 'procedural v1'],
              ['Saved', savedRev ? formatDateTime(savedRev.created_at) : '—'],
            ]}
            empty={
              <EmptyState icon="scan" title="No profile yet" compact>
                Describe the person, answer the guided questions, or compare witness accounts. The composite renders here as soon as there is something to draw.
              </EmptyState>
            }
          />

          <section className="panel generate">
            <div className="generate__row">
              <label className="field generate__note">
                <span className="label">Revision note (optional)</span>
                <input className="input input--sm" value={changeNote} maxLength={280} onChange={(e) => setChangeNote(e.target.value)} placeholder="What changed and why" />
              </label>
              <div className="generate__btns">
                {effectiveMode !== 'offline' && (
                  <button type="button" className="btn" onClick={() => save('offline')} disabled={Boolean(gen) || !renderable}>
                    <Icon name="cpu" /> Save offline composite
                  </button>
                )}
                <button type="button" className={`btn btn--lg ${effectiveMode === 'hosted' ? 'btn--blue' : 'btn--primary'}`}
                  onClick={() => save()} disabled={Boolean(gen) || !renderable || (!dirty && effectiveMode === 'offline')}>
                  {gen ? <span className="spinner" /> : <Icon name={effectiveMode === 'hosted' ? 'sparkle' : 'save'} />}
                  {gen ? (gen.mode === 'hosted' ? 'Waiting for hosted provider…' : 'Rendering & saving…') : primaryLabel}
                </button>
              </div>
            </div>
            {gen && (
              <div className="generate__progress" role="status">
                <div className="progress"><span className={gen.mode === 'offline' ? 'is-fast' : 'is-indeterminate'} /></div>
                <span className="mono faint">{provider?.label} · <Elapsed since={gen.since} /></span>
              </div>
            )}
            {!dirty && savedRev && !gen && effectiveMode === 'offline' && (
              <p className="faint generate__hint"><Icon name="check" /> Revision {savedRev.number} matches the current profile. Edit the profile to create a new revision.</p>
            )}
            {genError && (
              <div className="alert alert--error generate__error" role="alert">
                <Icon name="error" />
                <div>
                  <strong>{genError.mode === 'offline' ? 'Could not save' : `${providers[genError.mode]?.label} failed`}</strong>
                  <p>{genError.message}</p>
                  {genError.mode !== 'offline' && (
                    <button type="button" className="btn btn--sm" onClick={() => save('offline')}>
                      <Icon name="cpu" /> Use the offline composite instead
                    </button>
                  )}
                </div>
              </div>
            )}
          </section>

          {sketch && sketch.revisions.length > 0 && (
            <section className="panel revisions">
              <div className="panel__head">
                <h2 className="panel__title section-title">Revision history</h2>
                <a className="btn btn--ghost btn--sm" href={`#/compare?sketch=${encodeURIComponent(sketch.id)}`}><Icon name="compare" /> Compare</a>
              </div>
              <ol className="revisions__list">
                {[...sketch.revisions].reverse().map((r) => (
                  <li key={r.number}>
                    <button type="button" className={`rev ${r.number === viewingRev ? 'is-active' : ''}`} onClick={() => openRevision(r)}>
                      <img src={assetUrl(r.image_url)} alt={`Revision ${r.number}`} loading="lazy" />
                      <span className="rev__meta">
                        <span className="mono rev__n">R{r.number}</span>
                        <span className={`tag ${r.is_ai ? 'tag--ai' : 'tag--procedural'}`}>{r.is_ai ? 'AI' : 'Procedural'}</span>
                      </span>
                      <span className="faint mono rev__time">{formatDateTime(r.created_at)}</span>
                      {r.change_note && <span className="rev__note">{r.change_note}</span>}
                    </button>
                  </li>
                ))}
              </ol>
            </section>
          )}

          <RenderNotes notes={notes} />
        </div>

        <div className="studio__side panel">
          <div className="tabs" role="tablist">
            {[['profile', 'Profile', 'list'], ['adjust', 'Editor', 'sliders'], ['refine', 'Refine', 'wand']].map(([id, label, icon]) => (
              <button key={id} type="button" role="tab" aria-selected={tab === id} className="tabs__tab" onClick={() => setTab(id)}>
                <Icon name={icon} /> {label}
              </button>
            ))}
          </div>
          <div className="studio__sidebody">
            {tab === 'profile' && <TraitPanel profile={profile} onChange={setProfile} revealKey={reveal} />}
            {tab === 'adjust' && <AdjustPanel profile={profile} onChange={setProfile} aiNotice={aiNotice} />}
            {tab === 'refine' && <RefinePanel profile={profile} onApply={onRefined} />}
          </div>
        </div>
      </div>
    </div>
  )
}
