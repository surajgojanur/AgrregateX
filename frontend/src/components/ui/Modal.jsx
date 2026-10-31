import { useEffect, useRef, useState } from 'react'
import Icon from './Icon'

const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]'

export const Modal = ({ title, children, onClose, footer, wide = false, labelledBy = 'modal-title' }) => {
  const ref = useRef(null)
  useEffect(() => {
    const prev = document.activeElement
    document.body.classList.add('is-locked')
    const first = ref.current?.querySelector(FOCUSABLE)
    first?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'Tab' && ref.current) {
        const nodes = [...ref.current.querySelectorAll(FOCUSABLE)]
        if (!nodes.length) return
        const [a, b] = [nodes[0], nodes[nodes.length - 1]]
        if (e.shiftKey && document.activeElement === a) { e.preventDefault(); b.focus() }
        else if (!e.shiftKey && document.activeElement === b) { e.preventDefault(); a.focus() }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.classList.remove('is-locked')
      prev?.focus?.()
    }
  }, [onClose])

  return (
    <div className="modal-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal panel panel--corners ${wide ? 'modal--wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={labelledBy} ref={ref}>
        <div className="panel__head">
          <h2 id={labelledBy} className="panel__title">{title}</h2>
          <button type="button" className="btn btn--ghost btn--icon btn--sm" onClick={onClose} aria-label="Close">
            <Icon name="close" />
          </button>
        </div>
        <div className="modal__body">{children}</div>
        {footer && <div className="modal__foot">{footer}</div>}
      </div>
    </div>
  )
}

export const ConfirmModal = ({ title, message, confirmLabel = 'Confirm', danger = false, requireText, onConfirm, onClose, busy }) => {
  const [typed, setTyped] = useState('')
  const ok = !requireText || typed === requireText
  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>Cancel</button>
          <button type="button" className={`btn ${danger ? 'btn--danger' : 'btn--primary'}`} disabled={!ok || busy} onClick={onConfirm}>
            {busy && <span className="spinner" />}
            {confirmLabel}
          </button>
        </>
      }
    >
      <div className="muted modal__message">{message}</div>
      {requireText && (
        <label className="field" style={{ marginTop: 14 }}>
          <span className="label">Type {requireText} to confirm</span>
          <input className="input mono" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        </label>
      )}
    </Modal>
  )
}
