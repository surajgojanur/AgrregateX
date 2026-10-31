import { useEffect, useRef, useState } from 'react'
import { witness, imageUrl, downloadUrl } from '../api/witnesstrace'
import { api } from '../api/client'
import { useApp } from '../state/AppContext'
import { useTheme } from '../lib/theme'
import { navigate } from '../lib/router'
import CompareSlider from '../components/sketch/CompareSlider'
import EmptyState from '../components/ui/EmptyState'
import DictateButton from '../components/ui/DictateButton'

const empty = () => ({ value: null, confidence: 'unknown', source: 'operator', quote: '' })
const clone = value => structuredClone(value)
const key = () => crypto.randomUUID().replaceAll('-', '')
const call = (record, suffix, body, method) => witness.operation(`/api/cases/${record.id}${suffix}`, body, method)

const WORKSPACE = { text: 'Generated', lab: 'Character Lab', refinement: 'Refinement', sketch: 'Artist edit', upload: 'Imported', enhance: 'Enhanced' }

export function RevisionList() {
  const { wt } = useApp()
  const r = wt.record
  const seen = useRef({ id: null, ids: new Set() })
  const [fresh, setFresh] = useState({ ids: [], note: '' })
  // Only revisions that appear while this list is open count as newly saved.
  useEffect(() => {
    if (!r) return
    const ids = r.versions.map(v => v.id)
    if (seen.current.id !== r.id) { seen.current = { id: r.id, ids: new Set(ids) }; return }
    const added = ids.filter(id => !seen.current.ids.has(id))
    added.forEach(id => seen.current.ids.add(id))
    if (added.length) setFresh({ ids: added, note: added.map(id => `Revision V${ids.indexOf(id) + 1} saved`).join('. ') })
  }, [r])
  useEffect(() => {
    if (!fresh.ids.length) return undefined
    const timer = setTimeout(() => setFresh(f => ({ ...f, ids: [] })), 2600)
    return () => clearTimeout(timer)
  }, [fresh.ids])
  if (r && !r.versions.length) return <EmptyState compact art="timeline" title="No revisions yet">Generated, edited and imported images appear here as immutable revisions.</EmptyState>
  return <div className="wt-fields"><p className="sr-only" role="status">{fresh.note}</p>{r?.versions.map((v, i) => <div key={v.id} className={`wt-revision ${fresh.ids.includes(v.id) ? 'is-new' : ''} ${r.selected_version_id === v.id ? 'is-selected' : ''}`}><img src={imageUrl(v)} alt={`Revision ${i + 1}`} loading="lazy" /><div>{fresh.ids.includes(v.id) && <span className="wt-revision__saved" aria-hidden="true">Revision saved</span>}<button className="btn btn--sm" disabled={wt.busy} aria-pressed={r.selected_version_id === v.id} onClick={() => wt.update(() => call(r, '/selection', { version_id: v.id }))}>Select V{i + 1}</button><button className="btn btn--sm" disabled={wt.busy} onClick={() => wt.update(() => call(r, '/selection', { version_id: v.id, preferred: true }))}>{r.preferred_version_id === v.id ? '★ Preferred' : 'Set preferred'}</button><p className="mono wt-id">{v.workspace} · {v.id}<br />Parent: {v.parent_id || 'original'}<br />SHA-256: {v.sha256}</p><a href={imageUrl(v)} target="_blank" rel="noreferrer">Full resolution</a> · <a href={downloadUrl(r.id, v.id)} download>PNG</a></div></div>)}</div>
}

export function CharacterLab() {
  const { wt } = useApp()
  const r = wt.record
  const [groups, setGroups] = useState([])
  const [draft, setDraft] = useState(() => clone(r.draft))
  const [undo, setUndo] = useState([])
  const [review, setReview] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { let active = true; witness.operation('/api/lab-schema').then(s => { if (active) setGroups(s.groups) }).catch(e => { if (active) setError(e.message) }); return () => { active = false } }, [])
  const change = next => { setUndo(u => [...u.slice(-29), clone(draft)]); setDraft(next); setReview(null) }
  const edit = (f, a) => { const next = clone(draft); next[f.shared ? 'attributes' : 'lab'][f.key] = a; change(next) }
  const save = async () => {
    const saved = await call(r, '', { revision: r.revision, draft }, 'PUT')
    return saved
  }
  return <section className="panel"><div className="panel__head"><h2 className="panel__title">Character Lab · 45 attributes</h2></div><div className="panel__body wt-fields">
    <p>Seven groups. Unknown stays unspecified. Controls are relative prompt requests, not measurements. Only Update Preview starts generation.</p>
    <label>Output style<select value={draft.style} onChange={e => change({ ...draft, style: e.target.value })}><option value="forensic">Forensic sketch</option><option value="portrait">Realistic illustration</option></select></label>
    <label>Framing<select value={draft.view} onChange={e => change({ ...draft, view: e.target.value })}>{['Portrait', '16:9', 'Upper Body'].map(v => <option key={v}>{v}</option>)}</select></label>
    {groups.map(group => <details key={group.id}><summary>{group.label} · {group.fields.length}</summary><button className="btn btn--sm" onClick={() => { const next = clone(draft); group.fields.forEach(f => { next[f.shared ? 'attributes' : 'lab'][f.key] = empty() }); change(next) }}>Reset group to Unknown</button>{group.fields.map(f => {
      const a = draft[f.shared ? 'attributes' : 'lab'][f.key] || empty()
      return <div className={`wt-lab-field is-${a.value === null ? 'unknown' : a.confidence} from-${a.source}`} key={f.key}><label htmlFor={'trait-' + f.key}>{f.label} <span className="mono">{a.value ?? 'Unknown'}</span></label>
        {f.kind === 'select' ? <select id={'trait-' + f.key} value={a.value || ''} onChange={e => edit(f, { ...a, value: e.target.value || null, confidence: e.target.value ? 'tentative' : 'unknown' })}><option value="">Unknown / not provided</option>{f.options.map(o => <option key={o}>{o}</option>)}</select> : <><input id={'trait-' + f.key} type={f.kind === 'slider' ? 'range' : f.kind === 'age' ? 'number' : 'text'} min={f.kind === 'age' ? 18 : 0} max={f.kind === 'age' ? 100 : 100} maxLength={100} value={a.value ?? (f.kind === 'slider' ? 50 : '')} onChange={e => edit(f, { ...a, value: e.target.value || null, confidence: e.target.value ? 'tentative' : 'unknown' })} /><button className="btn btn--sm" onClick={() => edit(f, empty())}>Unknown</button>{f.kind === 'slider' && <small>{f.low} → {f.high} · 50 neutral</small>}</>}
        <label>Recollection<select aria-label={f.label + ' confidence'} value={a.confidence} disabled={a.value === null} onChange={e => edit(f, { ...a, confidence: e.target.value })}>{a.value === null && <option value="unknown">Unknown</option>}<option value="tentative">Tentative</option><option value="certain">Certain</option></select></label>
        <label>Source<select aria-label={f.label + ' source'} value={a.source} disabled={a.value === null} onChange={e => edit(f, { ...a, source: e.target.value })}><option value="operator">Operator</option><option value="witness">Witness quote</option></select></label>{a.source === 'witness' && <label>Exact recorded quote<input value={a.quote} maxLength={1800} onChange={e => edit(f, { ...a, quote: e.target.value })} /></label>}
      </div>
    })}</details>)}
    <button className="btn" disabled={!undo.length} onClick={() => { setDraft(undo.at(-1)); setUndo(undo.slice(0, -1)); setReview(null) }}>Undo lab edit</button>
    <button className="btn" disabled={wt.busy} onClick={() => wt.update(save)}>Save draft</button>
    <button className="btn" onClick={async () => { try { setReview(await call(r, '/prompt-preview', draft)); setError('') } catch (e) { setError(e.message) } }}>Review prompt</button>
    {review && <><pre className="wt-prompt">{review.description}</pre><p>{review.length} / {review.limit} characters{review.over_limit ? ' · Too long' : ''}</p></>}
    <button className="btn btn--primary" disabled={wt.busy || !review || review.over_limit || wt.job?.status === 'working'} onClick={() => wt.update(async () => { const saved = await save(); const handle = await witness.submitGeneration({ description: review.description, style: review.style, case_id: r.id, case_revision: saved.revision, workspace: 'lab' }); wt.follow(handle); return handle })}>Update Preview</button>
    {error && <p role="alert">{error}</p>}
  </div></section>
}

export function Refinement() {
  const { wt } = useApp(); const r = wt.record
  const [instruction, setInstruction] = useState(''); const [review, setReview] = useState(null); const [error, setError] = useState('')
  const parent = r.selected_version_id || r.versions.at(-1)?.id
  const payload = () => ({ parent_id: parent, instruction, draft: r.draft, revision: r.revision, request_key: key() })
  return <section className="panel"><div className="panel__head"><h2 className="panel__title">Refine selected revision</h2></div><div className="panel__body wt-fields"><p>Text regeneration creates an immutable child revision. Visual identity can drift.</p><span className="merge__wlabel"><span className="label">Refinement instructions</span><DictateButton value={instruction} maxLength={1800} onChange={v => { setInstruction(v); setReview(null) }} /></span><textarea aria-label="Refinement instructions" maxLength={1800} value={instruction} onChange={e => { setInstruction(e.target.value); setReview(null) }} /><button className="btn" disabled={!parent || !instruction.trim()} onClick={async () => { try { const body = payload(); const prompt = await call(r, '/refinement-preview', body); setReview({ body, prompt }); setError('') } catch (e) { setError(e.message) } }}>Review refinement prompt</button>{review && <pre className="wt-prompt">{review.prompt.description}</pre>}<button className="btn btn--primary" disabled={wt.busy || wt.job?.status === 'working' || !review || review.prompt.over_limit || review.body.parent_id !== parent || review.body.revision !== r.revision} onClick={() => wt.update(async () => { const handle = await call(r, '/refine', { ...review.body, reviewed_prompt: review.prompt.description }); wt.follow(handle); setReview(null); return handle })}>Generate refinement</button>{error && <p role="alert">{error}</p>}</div></section>
}

export function ProcessingTools() {
  const { wt } = useApp(); const [tool, setTool] = useState('sketch'); const [opened, setOpened] = useState(false); const frame = useRef(null)
  const open = name => { if (opened && frame.current?.contentWindow) { const w = frame.current.contentWindow; w.document.documentElement.dataset.tool = name; w.selectTab?.(name); } else { setTool(name); setOpened(true) } }
  const id = wt.record.id
  useEffect(() => {
    const guard = e => {
      const w = frame.current?.contentWindow
      if ((w?.Sketchpad?.isDirty() || w?.Enhance?.isDirty()) && !window.confirm('Discard unsaved image edits and switch cases?')) e.preventDefault()
    }
    window.addEventListener('witness-before-case', guard)
    return () => window.removeEventListener('witness-before-case', guard)
  }, [id])
  return <section className="panel wt-process"><div className="panel__head"><h2 className="panel__title">Image editing</h2></div><div className="panel__body wt-fields"><p>The preserved editing engine keeps layers and exact enhancement pixels. Canvas state stays open during navigation. Save edits to retain them after refresh or case switching.</p><div><button className="btn" onClick={() => { open('sketch') }}>Digital Sketchpad</button> <button className="btn" onClick={() => { open('enhance') }}>Enhance</button> <button className="btn" onClick={wt.refresh}>Reload saved revisions</button></div>{opened && <iframe ref={frame} className="wt-tool-frame" title="WitnessTrace image editing" src={`/wt-api/tools/index.html?case=${id}&tool=${tool}`} />}</div></section>
}

export function Deliverables() {
  const { wt } = useApp(); const r = wt.record
  const [reports, setReports] = useState(null); const [views, setViews] = useState(null); const [error, setError] = useState('')
  const selected = r.selected_version_id || r.versions.at(-1)?.id
  const run = async op => { try { setError(''); return await op() } catch (e) { setError(e.message) } }
  return <section className="panel"><div className="panel__head"><h2 className="panel__title">Multi-view & case reports</h2></div><div className="panel__body wt-fields"><p>AI-generated 2D interpretations, not geometrically accurate reconstructed 3D models.</p>
    <button className="btn" onClick={() => run(async () => setViews(await call(r, '/multiview')))}>Load saved angle sheets</button>
    {views?.requests.map(view => <div key={view.job_id}><p className="mono wt-id">{view.created_at} · {view.status} · Parent {view.parent_id}</p>{view.image_url && <a href={imageUrl({id: view.job_id, image_url: view.image_url})} target="_blank" rel="noreferrer"><img className="wt-sheet-thumb" src={imageUrl({id: view.job_id, image_url: view.image_url})} alt="Saved 2D concept sheet" /></a>}</div>)}
    <p>Angle generation and reviewed crops are available in the preserved multi-view workspace below.</p>
    <details><summary>Multi-view workspace</summary><iframe className="wt-tool-frame" title="WitnessTrace multi-view and reports" src={`/wt-api/tools/index.html?case=${r.id}&tool=multiview`} /></details>
    {selected && <p><a href={downloadUrl(r.id, selected)} download>Download PNG</a> · <a href={`/wt-api/api/cases/${r.id}/versions/${selected}/export.json`} download>Download case JSON</a></p>}
    <button className="btn" disabled={!selected || wt.busy} onClick={() => run(async () => { await call(r, '/reports', { version_id: selected, request_key: key() }); setReports(await call(r, '/reports')); window.dispatchEvent(new Event('witness-reports')) })}>Create PDF report</button><button className="btn" onClick={() => run(async () => setReports(await call(r, '/reports')))}>Load persisted reports</button>
    {reports?.length === 0 && <EmptyState compact art="document" title="No reports yet">Create a PDF report to save the selected revision with its testimony, attributes and history.</EmptyState>}
    {reports?.map(report => <div key={report.id} className="wt-fields wt-report"><span className="mono wt-id">{report.id} · {report.created_at}</span>{['pdf', 'json', 'png'].map(ext => <a key={ext} href={`/wt-api/api/cases/${r.id}/reports/${report.id}/${ext}`} download>Download {ext.toUpperCase()}</a>)}</div>)}{error && <p role="alert">{error}</p>}
  </div></section>
}

export function WitnessLibrary() {
  const { wt } = useApp(); const [search, setSearch] = useState(''); const [records, setRecords] = useState({})
  useEffect(() => {
    const controller = new AbortController()
    Promise.allSettled(wt.cases.map(c => witness.getCase(c.id, controller.signal))).then(results => {
      if (!controller.signal.aborted) setRecords(Object.fromEntries(results.filter(r => r.status === 'fulfilled').map(r => [r.value.id, r.value])))
    })
    return () => controller.abort()
  }, [wt.cases])
  const shown = wt.cases.filter(c => c.title.toLowerCase().includes(search.toLowerCase()))
  const empty = !wt.cases.length
    ? <EmptyState art={wt.connection ? 'document' : 'connection'} title={wt.connection ? 'No cases yet' : 'Case library unavailable'} action={wt.connection
      ? <button className="btn btn--primary" onClick={() => navigate('new')}>Create a case</button>
      : <button className="btn" onClick={wt.reconnect}>Reconnect</button>}>
      {wt.connection ? 'Cases you create in New Sketch appear here with their saved images and revisions.' : wt.error || 'WitnessTrace is not connected.'}
    </EmptyState>
    : !shown.length && <EmptyState compact art="search" title={`No cases match “${search}”`} action={<button className="btn btn--sm" onClick={() => setSearch('')}>Clear search</button>} />
  return <div className="wt-fields"><div className="toolbar panel"><h2>Case library</h2><input aria-label="Search cases" placeholder="Search case titles" value={search} onChange={e => setSearch(e.target.value)} />{wt.cases.length > 0 && <span className="mono faint lib-count" role="status">{search ? `${shown.length} of ${wt.cases.length} cases` : `${wt.cases.length} case${wt.cases.length === 1 ? '' : 's'}`}</span>}</div>{empty && <section className="panel lib-empty">{empty}</section>}<div className="library__grid">{shown.map((c, index) => {
    const record = records[c.id]; const v = record?.versions.find(v => v.id === record.selected_version_id) || record?.versions.at(-1)
    return <article className={`lib-card panel lib-card--enter ${c.id === wt.record?.id ? 'is-active' : ''}`} style={{ '--i': Math.min(index, 10) }} key={c.id}><button className="lib-card__img" onClick={() => wt.select(c.id)} aria-label={'Select ' + c.title}>{v ? <img src={imageUrl(v)} alt={'Saved composite for ' + c.title} loading="lazy" /> : <span>{record ? 'No saved image' : 'Loading saved image…'}</span>}</button><div className="lib-card__body"><h3 className="lib-card__title">{c.title}</h3><p className="lib-card__meta mono wt-id">{c.id}</p><p>{c.synthetic ? 'Synthetic' : 'Witness case'} · {c.frozen_at ? 'Original frozen' : 'Original draft'} · {record?.versions.length ?? '…'} revisions</p><p className="mono">{c.created_at}</p><div className="lib-card__actions"><button className="btn btn--sm" disabled={wt.busy} onClick={() => wt.select(c.id)} aria-pressed={c.id === wt.record?.id}>Select case</button><button className="btn btn--sm" onClick={async () => { await wt.select(c.id); navigate('new') }}>Open studio</button></div></div></article>
  })}</div>{wt.record && <><h3>{wt.record.title}</h3><RevisionList /><details><summary>Persisted case activity</summary>{wt.record.events.map(event => <p className="mono wt-id" key={event.id}>{event.created_at} · {event.kind} · {event.detail}</p>)}</details><Deliverables /></>}</div>
}

const valueText = value => (value === null || value === undefined || value === '' ? 'Unknown' : String(value))

// Differences in recorded attributes between two saved snapshots. No similarity score.
function traitChanges(a, b) {
  if (!a || !b) return null
  const fields = { ...a.attributes, ...a.lab, ...b.attributes, ...b.lab }
  const pick = (snap, k) => (snap.attributes?.[k] ?? snap.lab?.[k])?.value ?? null
  const changed = []; let same = 0
  for (const k of Object.keys(fields)) {
    const from = pick(a, k); const to = pick(b, k)
    if (valueText(from) !== valueText(to)) changed.push({ key: k, from, to })
    else if (from !== null && from !== '') same += 1
  }
  for (const k of ['style', 'view']) if (a[k] !== b[k]) changed.push({ key: k, from: a[k], to: b[k] })
  return { changed, same }
}

export function WitnessCompare() {
  const { wt } = useApp(); const versions = wt.record?.versions || []
  const [a, setA] = useState(''); const [b, setB] = useState(''); const [mode, setMode] = useState('slider')
  const [labels, setLabels] = useState({}); const [labelError, setLabelError] = useState('')
  useEffect(() => {
    let active = true
    witness.operation('/api/lab-schema').then(s => { if (active) setLabels(Object.fromEntries(s.groups.flatMap(g => g.fields.map(f => [f.key, f.label])))) }, e => { if (active) setLabelError(e.message) })
    return () => { active = false }
  }, [])
  const before = versions.find(v => v.id === a) || versions.at(-2); const after = versions.find(v => v.id === b) || versions.at(-1)
  const n = v => versions.findIndex(x => x.id === v.id) + 1
  const tag = v => `V${n(v)} · ${WORKSPACE[v.workspace] || v.workspace}`
  const diff = before && after && before.id !== after.id ? traitChanges(before.attribute_snapshot, after.attribute_snapshot) : null
  const name = k => labels[k] || { style: 'Output style', view: 'Framing' }[k] || k.replace(/_/g, ' ')
  return <section className="panel"><div className="panel__body wt-fields"><h2>Compare saved revisions</h2>
    {versions.length < 2 ? <EmptyState compact art="compare" title="Nothing to compare yet">Select a case with at least two saved revisions.</EmptyState> : <>
      <div className="wt-compare__controls">{['Before', 'After'].map((label, i) => <label key={label}>{label}<select value={(i ? after : before)?.id || ''} onChange={e => (i ? setB : setA)(e.target.value)}>{versions.map((v, k) => <option value={v.id} key={v.id}>V{k + 1} · {v.workspace} · {v.id.slice(0, 8)}</option>)}</select></label>)}
        <div className="segmented" role="group" aria-label="Comparison view">{[['slider', 'Slider'], ['split', 'Side by side']].map(([id, label]) => <button key={id} type="button" aria-pressed={mode === id} onClick={() => setMode(id)}>{label}</button>)}</div></div>
      <div className="wt-compare__view">{mode === 'split'
        ? <div className="wt-side-by-side">{[before, after].map((v, i) => <figure key={i}><img src={imageUrl(v)} alt={`${i ? 'After' : 'Before'} revision ${tag(v)}`} /><figcaption className="mono">{i ? 'After' : 'Before'} · {tag(v)}</figcaption></figure>)}</div>
        : <CompareSlider before={imageUrl(before)} after={imageUrl(after)} beforeLabel={`Before · ${tag(before)}`} afterLabel={`After · ${tag(after)}`} />}</div>
      <div className="wt-compare__summary" aria-live="polite">
        <h3 className="label">Recorded attribute changes · V{n(before)} → V{n(after)}</h3>
        {before.id === after.id ? <p className="faint">The same revision is selected on both sides.</p>
          : !diff ? <p className="faint">An attribute snapshot is not available for one of these revisions.</p>
            : diff.changed.length ? <ul className="wt-diff">{diff.changed.map(c => <li key={c.key}><span>{name(c.key)}</span><span className="mono wt-diff__from">{valueText(c.from)}</span><span aria-hidden="true">→</span><span className="sr-only">changed to</span><span className="mono wt-diff__to">{valueText(c.to)}</span></li>)}</ul>
              : <p className="faint">No recorded attribute differs. Image differences come from generation or editing.</p>}
        {diff && <p className="faint mono wt-id">{diff.changed.length} changed · {diff.same} recorded attributes unchanged{labelError ? ' · field names unavailable' : ''}</p>}
        <p className="faint">Lists recorded attribute values only. No similarity or identity score is computed.</p>
      </div>
    </>}<RevisionList /></div></section>
}

const HAS_BROWSER_SPEECH = typeof window !== 'undefined' && Boolean(window.SpeechRecognition || window.webkitSpeechRecognition)

export function WitnessSettings() {
  const { wt, prefs, updatePrefs, health, refreshHealth } = useApp(); const [theme, changeTheme] = useTheme()
  const [speech, setSpeech] = useState(null)
  const [checking, setChecking] = useState(false)
  const [checkedAt, setCheckedAt] = useState(null)
  const loadSpeech = () => api.speech().then(setSpeech, () => setSpeech({ available: false }))
  useEffect(() => { loadSpeech(); setCheckedAt(new Date()) }, [])
  const recheck = async () => {
    setChecking(true)
    try { await Promise.all([wt.reconnect(), refreshHealth(), loadSpeech()]) } finally { setChecking(false); setCheckedAt(new Date()) }
  }
  const c = wt.connection
  const rows = [
    ['Revelio engine', health ? 'ok' : 'err', health ? `Online · v${health.version}` : 'Offline', 'Accounts, sessions and the gateway to WitnessTrace.'],
    ['WitnessTrace', c ? 'ok' : 'err', c ? 'Connected' : 'Not connected', c ? 'Cases, testimony, images and reports.' : wt.error || 'The case service is not reachable.'],
    ['Codex CLI', c?.codex_installed ? 'ok' : 'warn', c?.codex_installed ? 'Installed' : 'Not found', c?.codex_installed ? 'Sign-in and quota are only confirmed by a real generation.' : 'AI generation needs the Codex CLI signed in on this machine.'],
    ['Dictation', speech?.available ? 'ok' : speech && HAS_BROWSER_SPEECH ? 'warn' : speech ? 'err' : 'idle',
      !speech ? 'Checking…' : speech.available ? `Local · ${speech.model}` : HAS_BROWSER_SPEECH ? 'Browser speech service' : 'Unavailable',
      !speech ? '' : speech.available ? 'Audio is transcribed on this machine and never sent elsewhere.' : 'Server-side dictation needs a backend. The browser service sends audio to its vendor and may fail outside Chrome, Edge and Safari.'],
  ]
  return <div className="wt-settings">
    <section className="panel"><div className="panel__head"><h2 className="panel__title">Application settings</h2></div><div className="panel__body wt-fields">
      <div className="field"><span className="label" id="wt-theme">Interface theme</span><div className="segmented wt-theme" role="group" aria-labelledby="wt-theme">{[['dark', 'Dark'], ['light', 'Light']].map(([id, label]) => <button key={id} type="button" aria-pressed={theme === id} onClick={() => changeTheme(id)}>{label}</button>)}</div></div>
      <label className="switch"><input type="checkbox" checked={prefs.reduceMotion} onChange={e => updatePrefs({ reduceMotion: e.target.checked })} /><span className="switch__track" aria-hidden="true" /><span><strong>Reduce motion</strong><span className="faint">Also follows your operating-system setting automatically.</span></span></label>
    </div></section>
    <section className="panel"><div className="panel__head"><h2 className="panel__title">System status</h2><button className="btn btn--sm" onClick={recheck} disabled={checking}>{checking ? <span className="spinner" /> : null}{checking ? 'Checking…' : 'Check again'}</button></div><div className="panel__body wt-fields">
      <ul className="wt-status-list">{rows.map(([name, state, value, note]) => <li key={name}><span className={`dot dot--${state}`} aria-hidden="true" /><div><span className="wt-status-list__name">{name}</span>{note && <span className="faint">{note}</span>}</div><strong>{value}</strong></li>)}</ul>
      {checkedAt && <p className="faint mono wt-id">Last checked {checkedAt.toLocaleTimeString()}</p>}
      {c && <details><summary>Raw diagnostics</summary><pre className="wt-prompt">{JSON.stringify({ revelio: health && { version: health.version, status: health.status }, witnesstrace: c, speech }, null, 2)}</pre></details>}
    </div></section>
    <section className="panel"><div className="panel__head"><h2 className="panel__title">Data</h2></div><div className="panel__body"><p className="muted">WitnessTrace owns cases, testimony, images and reports in its configured SQLite and file store. Revelio owns local account sessions and interface preferences. Signed-in users share this local collection.</p>{c?.generated_images_directory && <p className="faint mono wt-id">Codex images: {c.generated_images_directory}</p>}</div></section>
  </div>
}
