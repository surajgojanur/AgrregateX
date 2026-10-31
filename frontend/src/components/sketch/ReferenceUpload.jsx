import { useRef, useState } from 'react'
import Icon from '../ui/Icon'

const TYPES = ['image/png', 'image/jpeg', 'image/webp']
const MAX_MB = 5

/** Optional reference image. Only offered when the selected mode supports it. */
const ReferenceUpload = ({ value, onChange, supported, providerLabel }) => {
  const input = useRef(null)
  const [error, setError] = useState(null)

  const pick = (file) => {
    setError(null)
    if (!file) return
    if (!TYPES.includes(file.type)) return setError('Use a PNG, JPEG or WebP image.')
    if (file.size > MAX_MB * 1024 * 1024) return setError(`The image must be under ${MAX_MB} MB.`)
    const reader = new FileReader()
    reader.onload = () => onChange({ dataUrl: reader.result, name: file.name, size: file.size })
    reader.onerror = () => setError('The file could not be read.')
    reader.readAsDataURL(file)
  }

  return (
    <section className="panel reference" aria-labelledby="ref-title">
      <div className="panel__head">
        <h2 id="ref-title" className="panel__title section-title">Reference image</h2>
        <span className="label">Optional</span>
      </div>
      <div className="panel__body">
        {!supported ? (
          <p className="faint reference__off">
            <Icon name="lock" /> {providerLabel} does not use reference images. Choose a mode that supports them (Hosted AI) to attach one.
          </p>
        ) : (
          <>
            <input ref={input} type="file" accept={TYPES.join(',')} className="sr-only" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
            {value ? (
              <div className="reference__item">
                <img src={value.dataUrl} alt="Reference attachment preview" />
                <div className="reference__info">
                  <span className="mono">{value.name}</span>
                  <span className="faint mono">{(value.size / 1024).toFixed(0)} KB</span>
                  <div className="reference__btns">
                    <button type="button" className="btn btn--sm" onClick={() => input.current?.click()}>Replace</button>
                    <button type="button" className="btn btn--ghost btn--sm" onClick={() => onChange(null)}>Remove</button>
                  </div>
                </div>
              </div>
            ) : (
              <button type="button" className="dropzone" onClick={() => input.current?.click()}
                onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files?.[0]) }}>
                <Icon name="upload" />
                <span>Drop or choose an image</span>
                <span className="faint mono">PNG · JPEG · WebP · ≤ {MAX_MB} MB</span>
              </button>
            )}
            {error && <p className="field__error" role="alert">{error}</p>}
            <p className="field__hint">
              Sent to the hosted provider with this one request as visual context, after the server re-encodes it to strip
              metadata. It is never stored, and Revelio performs no face recognition or identity matching.
            </p>
          </>
        )}
      </div>
    </section>
  )
}

export default ReferenceUpload
