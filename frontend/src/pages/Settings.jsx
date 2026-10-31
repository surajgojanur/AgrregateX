import { useEffect, useState } from 'react'
import { api } from '../api/client'
import Icon from '../components/ui/Icon'
import { ConfirmModal } from '../components/ui/Modal'
import { safeStorage } from '../lib/format'
import { useApp } from '../state/AppContext'

const ICON = { offline: 'cpu', local: 'layers', hosted: 'cloud' }

export default function Settings() {
  const { providers, prefs, updatePrefs, notify, refreshHealth, health } = useApp()
  const [storage, setStorage] = useState(null)
  const [wipe, setWipe] = useState(false)
  const [busy, setBusy] = useState(false)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    api.storage().then(setStorage).catch(() => setStorage(null))
  }, [])

  const deleteAll = async () => {
    setBusy(true)
    try {
      const r = await api.deleteAll()
      safeStorage.remove('revelio.draft')
      notify({ kind: 'ok', title: 'Local data deleted', message: `${r.deleted_sketches} sketch(es), all revisions, images and activity were removed.` })
      setWipe(false)
    } catch (err) {
      notify({ kind: 'error', title: 'Delete failed', message: err.message })
    } finally {
      setBusy(false)
    }
  }

  const recheck = async () => {
    setChecking(true)
    await refreshHealth()
    setChecking(false)
  }

  return (
    <div className="settings reveal">
      <section className="panel" aria-labelledby="prov-title">
        <div className="panel__head">
          <h2 id="prov-title" className="panel__title section-title">Generation providers</h2>
          <button type="button" className="btn btn--ghost btn--sm" onClick={recheck} disabled={checking}>
            {checking ? <span className="spinner" /> : <Icon name="reset" />} Re-check
          </button>
        </div>
        <div className="panel__body providers stagger">
          {['offline', 'local', 'hosted'].map((id) => {
            const p = providers[id]
            if (!p) return null
            return (
              <article key={id} className={`provider ${p.available ? 'is-ready' : ''}`}>
                <div className="provider__head">
                  <span className="provider__icon"><Icon name={ICON[id]} /></span>
                  <div>
                    <h3>{p.label}</h3>
                    <div className="provider__tags">
                      <span className={`tag ${p.runs_locally ? 'tag--local' : 'tag--remote'}`}>{p.runs_locally ? 'Runs locally' : 'Remote service'}</span>
                      <span className={`tag ${p.kind === 'ai' ? 'tag--ai' : 'tag--procedural'}`}>{p.kind === 'ai' ? 'AI model' : 'Procedural'}</span>
                      {p.supports_reference_image && <span className="tag">Reference images</span>}
                      {p.supports_live_edit && <span className="tag">Live editing</span>}
                    </div>
                  </div>
                  <span className={`chip ${p.available ? 'chip--green' : ''}`}><span className={`dot ${p.available ? 'dot--ok' : 'dot--idle'}`} />{p.available ? 'Ready' : p.state.replace('_', ' ')}</span>
                </div>
                <p className="muted">{p.reason}</p>
                <p className={p.data_leaves_device ? 'text-amber provider__data' : 'provider__data text-green'}>
                  <Icon name={p.data_leaves_device ? 'cloud' : 'shield'} />
                  {p.data_leaves_device
                    ? 'When used, the trait-based prompt and any reference image are sent to Google. Usage may be billed.'
                    : 'No data leaves this device.'}
                </p>
                {id === 'hosted' && (
                  <pre className="code mono">{`# backend/.env  (git-ignored; never put keys in the frontend)\nREVELIO_HOSTED_PROVIDER=gemini\nGEMINI_API_KEY=…\nGEMINI_IMAGE_MODEL=${p.model || 'gemini-3-pro-image-preview'}`}</pre>
                )}
                {id === 'local' && p.detected && (
                  <ul className="provider__detect mono">
                    {Object.entries(p.detected).map(([k, v]) => <li key={k}><span className={`dot ${v ? 'dot--ok' : 'dot--idle'}`} /> {k}: {v ? 'found' : 'not found'}</li>)}
                  </ul>
                )}
              </article>
            )
          })}
        </div>
      </section>

      <div className="settings__grid">
        <section className="panel" aria-labelledby="privacy-title">
          <div className="panel__head"><h2 id="privacy-title" className="panel__title section-title">Data &amp; privacy</h2></div>
          <div className="panel__body privacy">
            <ul>
              <li><Icon name="shield" /> The offline composite generator, trait extraction and refinement run on this machine. They make no network requests.</li>
              <li><Icon name="database" /> Sketches are stored in a local SQLite database, with PNG and SVG files beside it. No account is required.</li>
              <li><Icon name="lock" /> The local engine listens on 127.0.0.1 only. It is not exposed to your network.</li>
              <li><Icon name="image" /> Reference images are validated, stripped of metadata and used for a single hosted request. They are never stored.</li>
              <li><Icon name="eyeOff" /> Revelio performs no face recognition, identity matching or attribute inference.</li>
              <li><Icon name="info" /> Your interface preferences and one unsaved draft are kept in this browser’s local storage.</li>
            </ul>
            {storage && (
              <dl className="kv">
                <dt className="label">Data directory</dt><dd className="mono">{storage.data_dir}</dd>
                <dt className="label">Engine</dt><dd className="mono">v{health?.version} · {health?.renderer}</dd>
              </dl>
            )}
          </div>
        </section>

        <section className="panel" aria-labelledby="ui-title">
          <div className="panel__head"><h2 id="ui-title" className="panel__title section-title">Interface</h2></div>
          <div className="panel__body prefs">
            <label className="switch">
              <input type="checkbox" checked={prefs.scanEffect} onChange={(e) => updatePrefs({ scanEffect: e.target.checked })} />
              <span className="switch__track" aria-hidden="true" />
              <span><strong>Scan-line effect while rendering</strong><span className="faint">A visual indicator only. It never modifies the image.</span></span>
            </label>
            <label className="switch">
              <input type="checkbox" checked={prefs.reduceMotion} onChange={(e) => updatePrefs({ reduceMotion: e.target.checked })} />
              <span className="switch__track" aria-hidden="true" />
              <span><strong>Reduce motion</strong><span className="faint">Also follows your operating-system setting automatically.</span></span>
            </label>
          </div>
        </section>

        <section className="panel danger-zone" aria-labelledby="danger-title">
          <div className="panel__head"><h2 id="danger-title" className="panel__title section-title">Delete local data</h2></div>
          <div className="panel__body">
            <p className="muted">Permanently removes every saved sketch, revision, image file and activity entry from this machine, plus the unsaved draft in this browser.</p>
            <button type="button" className="btn btn--danger" onClick={() => setWipe(true)}><Icon name="trash" /> Delete all local data…</button>
          </div>
        </section>
      </div>

      {wipe && (
        <ConfirmModal
          title="Delete all local data?"
          danger
          busy={busy}
          requireText="DELETE"
          confirmLabel="Delete everything"
          message="This permanently deletes all sketches, revisions, images and activity stored by Revelio on this machine. It cannot be undone."
          onConfirm={deleteAll}
          onClose={() => setWipe(false)}
        />
      )}
    </div>
  )
}
