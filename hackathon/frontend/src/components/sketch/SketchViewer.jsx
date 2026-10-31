import { useState } from 'react'
import { useApp } from '../../state/AppContext'
import Icon from '../ui/Icon'
import CompareSlider from './CompareSlider'

const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3]

/**
 * Large forensic viewing surface.
 * The scan line is a CSS overlay above the image; it never alters image pixels.
 */
const SketchViewer = ({ src, kind, label, sublabel, loading, error, before, onDownload, downloadBusy, meta = [], empty }) => {
  const { prefs } = useApp()
  const [failedImage, setFailedImage] = useState(null)
  const [zoom, setZoom] = useState(1)
  const [comparing, setComparing] = useState(false)
  const canCompare = Boolean(before?.src && src)
  const zi = ZOOMS.indexOf(zoom)
  const showCompare = comparing && canCompare

  return (
    <section className="viewer panel panel--corners" aria-label="Composite preview">
      <div className="viewer__bar">
        <div className="viewer__label">
          <span className={`tag ${kind === 'ai' ? 'tag--ai' : 'tag--procedural'}`}>
            {kind === 'ai' ? 'AI-generated' : 'Procedural · not AI'}
          </span>
          <span className="viewer__title">{label}</span>
          {sublabel && <span className="faint viewer__sub">{sublabel}</span>}
        </div>
        <div className="viewer__tools" role="toolbar" aria-label="Viewer controls">
          <button type="button" className="btn btn--ghost btn--icon btn--sm" disabled={zi <= 0 || showCompare} onClick={() => setZoom(ZOOMS[zi - 1])} aria-label="Zoom out"><Icon name="zoomOut" /></button>
          <button type="button" className="btn btn--ghost btn--sm mono viewer__zoom" onClick={() => setZoom(1)} disabled={showCompare} title="Fit to screen">{Math.round(zoom * 100)}%</button>
          <button type="button" className="btn btn--ghost btn--icon btn--sm" disabled={zi >= ZOOMS.length - 1 || showCompare} onClick={() => setZoom(ZOOMS[zi + 1])} aria-label="Zoom in"><Icon name="zoomIn" /></button>
          <button type="button" className="btn btn--ghost btn--icon btn--sm" onClick={() => setZoom(1)} disabled={showCompare} aria-label="Fit to screen"><Icon name="fit" /></button>
          <span className="viewer__sep" />
          <button type="button" className={`btn btn--sm ${showCompare ? 'btn--blue' : 'btn--ghost'}`} disabled={!canCompare}
            onClick={() => setComparing((v) => !v)} aria-pressed={showCompare} title={canCompare ? `Compare with ${before.label}` : 'Save a revision to compare versions'}>
            <Icon name="compare" /> Before / after
          </button>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onDownload} disabled={!src || downloadBusy}>
            {downloadBusy ? <span className="spinner" /> : <Icon name="download" />} PNG
          </button>
        </div>
      </div>

      <div className={`viewer__stage ${zoom > 1 ? 'is-zoomed' : ''} ${loading ? 'is-processing' : ''}`}>
        {loading && !showCompare && (
          <div className="viewer__processing" aria-hidden="true">
            <svg className="viewer__reticle" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="44" /><circle cx="60" cy="60" r="26" />
              <path d="M60 4v20M60 96v20M4 60h20M96 60h20" />
            </svg>
            {prefs.scanEffect && !src && <span className="viewer__sweep" />}
          </div>
        )}
        {showCompare ? (
          <div className="viewer__compare"><CompareSlider before={before.src} after={src} beforeLabel={before.label} afterLabel="Current" /></div>
        ) : src ? (
          <div className="viewer__frame" style={{ width: `${zoom * 100}%` }}>
            <img key={src} className="viewer__img" src={src} alt={`${label}. ${kind === 'ai' ? 'AI-generated image' : 'Procedural composite, not AI-generated'}`} draggable={false} onError={() => setFailedImage(src)} />
            {prefs.scanEffect && loading && <span className="viewer__scan" aria-hidden="true" />}
          </div>
        ) : (
          <div className="viewer__empty">{empty}</div>
        )}
        {loading && !showCompare && (
          <div className="viewer__busy mono" role="status"><span className="spinner" /> {kind === 'ai' ? 'Processing' : 'Rendering…'}</div>
        )}
        {(error || (src && failedImage === src)) && (
          <div className="viewer__error alert alert--error" role="alert"><Icon name="error" /><span>{error || 'Saved image could not be loaded. Reconnect to verify the revision.'}</span></div>
        )}
        <span className="viewer__corner viewer__corner--tl mono" aria-hidden="true">VIEW · {kind === 'ai' ? 'RASTER' : 'VECTOR'}</span>
      </div>

      {meta.length > 0 && (
        <dl className="viewer__meta">
          {meta.map(([k, v]) => (
            <div key={k}>
              <dt className="label">{k}</dt>
              <dd className="mono">{v}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}

export default SketchViewer
