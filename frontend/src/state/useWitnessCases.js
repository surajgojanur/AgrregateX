import { useCallback, useEffect, useRef, useState } from 'react'
import { pollJob, witness, witnessMode } from '../api/witnesstrace'
import { safeStorage } from '../lib/format'

export default function useWitnessCases() {
  const [record, setRecord] = useState(null)
  const [cases, setCases] = useState([])
  const [connection, setConnection] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [job, setJob] = useState(null)
  const lock = useRef(false)
  const epoch = useRef(0)
  const poller = useRef(null)
  const mounted = useRef(true)
  const follow = useCallback(async (caseId, jobId, ticket) => {
    poller.current?.abort()
    const controller = new AbortController()
    poller.current = controller
    try {
      const result = await pollJob(witness, jobId, { signal: controller.signal, onStatus: value => {
        if (mounted.current && epoch.current === ticket) setJob(value)
      } })
      const saved = await witness.getCase(caseId, controller.signal)
      if (!mounted.current || epoch.current !== ticket) return
      setRecord(saved)
      if (result.status === 'failed') setError(result.message || 'Generation failed. No new image was saved.')
      else if (!saved.versions.some(v => v.id === jobId)) setError('Job finished but its saved revision is missing. Reconnect.')
    } catch (e) { if (e.name !== 'AbortError' && mounted.current && epoch.current === ticket) setError(e.message) }
  }, [])
  const select = useCallback(async id => {
    const ticket = ++epoch.current
    poller.current?.abort()
    setError(''); setJob(null); setRecord(current => current?.id === id ? current : null)
    const saved = await witness.getCase(id)
    if (!mounted.current || epoch.current !== ticket) return
    safeStorage.set('revelio.witness.case', id)
    setRecord(saved)
    const pending = saved.jobs.find(j => j.status === 'working')
    if (pending) void follow(id, pending.id, ticket)
    else if (saved.jobs.at(-1)) setJob({ ...saved.jobs.at(-1), job_id: saved.jobs.at(-1).id })
    return saved
  }, [follow])
  const reconnect = useCallback(async () => {
    setError('')
    try {
      const health = await witness.health()
      const list = await witness.listCases()
      if (!mounted.current) return
      setConnection(health); setCases(list)
      const id = safeStorage.get('revelio.witness.case')
      if (id) await select(id)
    } catch (e) { if (mounted.current) { setConnection(null); setError(e.message) } }
  }, [select])
  useEffect(() => {
    mounted.current = true
    if (witnessMode) void reconnect()
    return () => { mounted.current = false; poller.current?.abort() }
  }, [reconnect])
  useEffect(() => {
    const sync = async event => {
      if (event.origin !== location.origin || event.data?.type !== 'witness-saved' || !/^[a-f0-9]{32}$/.test(event.data.caseId) || ![...document.querySelectorAll('iframe')].some(frame => frame.contentWindow === event.source)) return
      try {
        const saved = await witness.getCase(event.data.caseId)
        if (mounted.current) setRecord(current => current?.id === saved.id ? saved : current)
      } catch (e) { if (mounted.current) setError(e.message) }
    }
    window.addEventListener('message', sync)
    return () => window.removeEventListener('message', sync)
  }, [])
  const act = async operation => {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try { return await operation() } catch (e) { if (mounted.current) setError(e.message) }
    finally { lock.current = false; if (mounted.current) setBusy(false) }
  }
  return { record, cases, connection, error, busy, job, reconnect,
    refresh: () => act(() => select(record.id)),
    update: operation => act(async () => { const result = await operation(); await select(record.id); return result }),
    follow: handle => { setJob(handle); void follow(record.id, handle.job_id, epoch.current) },
    select: id => { if (!window.dispatchEvent(new Event('witness-before-case', { cancelable: true }))) return; return act(() => select(id)) },
    create: (title, synthetic = true) => act(async () => {
      const saved = await witness.createCase({ title, synthetic })
      setCases(await witness.listCases()); return select(saved.id)
    }),
    freeze: text => act(async () => { setRecord(await witness.freeze(record.id, record.revision, text)) }),
    clarify: (text, source) => act(async () => { setRecord(await witness.clarify(record.id, text, source)) }),
    generate: () => act(async () => {
      if (!record || job?.status === 'working') return
      // Read durable state first. Never automatically retry an accepted/ambiguous POST.
      const saved = await witness.getCase(record.id)
      if (saved.jobs.some(j => j.status === 'working')) { await select(saved.id); return }
      const prompt = await witness.preview(saved)
      if (prompt.over_limit) throw new Error('Prompt exceeds the 2,500-character limit. Review the case before generating.')
      const handle = await witness.submitGeneration({ description: prompt.description, style: prompt.style,
        case_id: saved.id, case_revision: saved.revision, workspace: 'text' })
      setJob(handle)
      void follow(saved.id, handle.job_id, epoch.current)
    }),
  }
}
