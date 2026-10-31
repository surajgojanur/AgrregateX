import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useApp } from '../../state/AppContext'
import Icon from './Icon'

const Recognition = typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null
const CAN_RECORD = typeof window !== 'undefined' && Boolean(window.MediaRecorder && navigator.mediaDevices?.getUserMedia)

// Embedded Electron views (VS Code's browser, desktop shells) and Brave expose the
// API but have no access to the speech service, so every attempt fails with "network".
const NO_SERVICE = typeof navigator !== 'undefined' && (/Electron\//.test(navigator.userAgent) || 'brave' in navigator)

const OPEN_ELSEWHERE = 'Open Revelio in Chrome, Edge or Safari to use dictation.'

const ERRORS = {
  'not-allowed': 'Microphone access was blocked. Allow it in the browser’s site settings to dictate.',
  'service-not-allowed': 'Speech recognition is disabled in this browser.',
  'audio-capture': 'No microphone was found.',
  network: `This browser could not reach its speech recognition service. Check your connection. ${OPEN_ELSEWHERE}`,
  'language-not-supported': 'Speech recognition does not support this language.',
}

// Longest single local recording; the server caps uploads as well.
const MAX_RECORD_MS = 3 * 60 * 1000

// Only one field dictates at a time; starting another stops the current one.
let active = null

// Whether the server transcribes locally (faster-whisper). Checked once per page load.
let localCheck = null
const checkLocal = () => {
  localCheck ||= CAN_RECORD ? api.speech().then((s) => Boolean(s.available), () => false) : Promise.resolve(false)
  return localCheck
}

// Appends a dictated phrase to existing text, starting a new sentence with a capital.
function append(base, phrase) {
  const text = phrase.trim()
  if (!text) return base
  const head = base.replace(/\s+$/, '')
  const sentence = !head || /[.!?]$/.test(head)
  const chunk = sentence ? text[0].toUpperCase() + text.slice(1) : text
  return head ? `${head} ${chunk}` : chunk
}

const clock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

// Speech-to-text for witness input. Prefers the server's local transcription, where the
// recording never leaves this machine; otherwise uses the browser's Web Speech API with
// live interim text. Renders nothing where neither is available.
const DictateButton = ({ value, onChange, maxLength, label = 'Dictate', lang }) => {
  const { notify } = useApp()
  const [local, setLocal] = useState(null) // null while checking
  const [listening, setListening] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [interim, setInterim] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const rec = useRef(null)
  const want = useRef(false)
  const latest = useRef({ value, onChange, maxLength })
  useEffect(() => { latest.current = { value, onChange, maxLength } })

  useEffect(() => {
    let alive = true
    checkLocal().then((ok) => alive && setLocal(ok))
    return () => { alive = false }
  }, [])

  useEffect(() => () => {
    want.current = false
    const r = rec.current
    rec.current = null // a recording still in progress is discarded, not transcribed
    if (r?.abort) r.abort()
    else if (r?.state === 'recording') r.stop()
    if (active === r) active = null
  }, [])

  if (!local && !Recognition) return null

  const language = () => lang || document.documentElement.lang || navigator.language || 'en-US'

  const insert = (phrase) => {
    const { value: v, onChange: set, maxLength: max } = latest.current
    const next = append(v, phrase)
    latest.current.value = max ? next.slice(0, max) : next
    set(latest.current.value)
  }

  const stop = () => {
    want.current = false
    rec.current?.stop()
  }

  const startLocal = async () => {
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (err) {
      const key = err?.name === 'NotAllowedError' ? 'not-allowed' : 'audio-capture'
      notify({ kind: 'error', title: 'Dictation unavailable', message: ERRORS[key] })
      return
    }
    if (active && active !== rec.current) active.stop()
    const r = new MediaRecorder(stream)
    const chunks = []
    const started = Date.now()
    const tick = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 500)
    const limit = setTimeout(() => r.state === 'recording' && r.stop(), MAX_RECORD_MS)
    r.ondataavailable = (e) => e.data.size && chunks.push(e.data)
    r.onstop = async () => {
      clearInterval(tick)
      clearTimeout(limit)
      stream.getTracks().forEach((t) => t.stop())
      setListening(false)
      if (active === r) active = null
      want.current = false
      if (rec.current !== r || !chunks.length) return // unmounted mid-recording
      setTranscribing(true)
      try {
        const { text } = await api.transcribe(new Blob(chunks, { type: r.mimeType }), language())
        if (text) insert(text)
        else notify({ kind: 'warn', title: 'No speech detected', message: 'Nothing was transcribed. Try again a little closer to the microphone.' })
      } catch (err) {
        notify({ kind: 'error', title: 'Transcription failed', message: err.message })
      } finally {
        setTranscribing(false)
      }
    }
    rec.current = r
    active = r
    want.current = true
    setElapsed(0)
    r.start()
    setListening(true)
  }

  const startBrowser = () => {
    if (NO_SERVICE) {
      notify({ kind: 'warn', title: 'Dictation unavailable here', message: `This browser has no speech recognition service. ${OPEN_ELSEWHERE}` })
      return
    }
    if (active && active !== rec.current) active.stop()
    const r = new Recognition()
    r.continuous = true
    r.interimResults = true
    r.lang = language()
    r.onresult = (e) => {
      let pending = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i]
        if (res.isFinal) insert(res[0].transcript)
        else pending += res[0].transcript
      }
      setInterim(pending)
    }
    r.onerror = (e) => {
      if (e.error === 'no-speech' || e.error === 'aborted') return
      want.current = false
      notify({ kind: 'error', title: 'Dictation stopped', message: ERRORS[e.error] || `Speech recognition error: ${e.error}` })
    }
    r.onend = () => {
      // Browsers end sessions after silence or a time limit; resume until the operator stops.
      if (want.current && rec.current === r) {
        try { r.start(); return } catch { /* fall through */ }
      }
      setListening(false)
      setInterim('')
      if (active === r) active = null
    }
    rec.current = r
    active = r
    want.current = true
    try {
      r.start()
      setListening(true)
    } catch {
      want.current = false
    }
  }

  const status = transcribing ? 'Transcribing…' : local ? `Recording ${clock(elapsed)} · press Stop when done` : interim || 'Listening…'

  return (
    <span className="dictate">
      {(listening || transcribing) && (
        <span className="dictate__live" aria-live="polite">
          {transcribing ? <span className="spinner" aria-hidden="true" /> : <span className="dictate__pulse" aria-hidden="true" />}
          <span className="dictate__interim">{status}</span>
        </span>
      )}
      <button
        type="button"
        className={`btn btn--sm ${listening ? 'btn--danger' : 'btn--ghost'}`}
        aria-pressed={listening}
        disabled={transcribing || local === null}
        onClick={listening ? stop : local ? startLocal : startBrowser}
        title={listening ? 'Stop dictation'
          : local ? 'Dictate with the microphone. Transcribed on this machine; the recording is not sent anywhere else.'
            : 'Dictate with the microphone. Uses the browser’s speech recognition service.'}
      >
        <Icon name={listening ? 'micOff' : 'mic'} /> {listening ? 'Stop' : label}
      </button>
    </span>
  )
}

export default DictateButton
