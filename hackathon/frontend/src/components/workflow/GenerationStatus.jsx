import Icon from '../ui/Icon'

const STAGES = ['Reading testimony', 'Extracting traits', 'Building composite', 'Rendering result', 'Verifying output']
const STATE_TEXT = { done: 'complete', active: 'in progress', fail: 'failed', idle: 'not started' }

// WitnessTrace reports one "working" phase for Codex, so building and rendering are
// shown together as in progress (indeterminate) rather than as invented sub-steps.
function stagesFor(job, saved, missing) {
  if (job.status === 'working') return ['done', 'done', 'active', 'active', 'idle']
  if (job.status === 'failed') return ['done', 'done', 'fail', 'idle', 'idle']
  if (saved) return ['done', 'done', 'done', 'done', 'done']
  return ['done', 'done', 'done', 'done', missing ? 'fail' : 'active']
}

/** Live, non-blocking status of the latest generation job in this case. */
export default function GenerationStatus({ job, versions = [], error }) {
  if (!job) {
    return <section className="panel gen-status is-idle"><div className="panel__body" role="status" aria-live="polite">No generation submitted in this case.</div></section>
  }
  const id = job.job_id || job.id
  const saved = versions.some((v) => v.id === id)
  const missing = job.status === 'complete' && !saved && Boolean(error)
  const states = stagesFor(job, saved, missing)
  const running = states.includes('active')
  return (
    <section className={`panel gen-status ${running ? 'is-running' : ''}`} aria-label="Generation progress">
      <div className="panel__body">
        <ol className="gen-status__stages">
          {STAGES.map((label, i) => (
            <li key={label} className={`gen-stage is-${states[i]}`}>
              <span className="gen-stage__node" aria-hidden="true">
                {states[i] === 'done' ? <Icon name="check" strokeWidth={2.4} /> : states[i] === 'fail' ? <Icon name="close" strokeWidth={2.4} /> : null}
              </span>
              <span className="gen-stage__label">{label}<span className="sr-only">: {STATE_TEXT[states[i]]}</span></span>
            </li>
          ))}
        </ol>
        {job.status === 'working' && (
          <div className="gen-status__bar" role="progressbar" aria-label="Codex generation" aria-valuetext="In progress, no step detail reported">
            <span />
          </div>
        )}
        <p className="gen-status__msg mono" role="status" aria-live="polite">
          {`${job.status === 'complete' && !saved ? 'Verifying saved output' : job.status} · ${job.message}`}
        </p>
        {job.status === 'working' && <p className="faint gen-status__hint">You can keep working or navigate away; the job continues and this panel resumes when you return.</p>}
      </div>
    </section>
  )
}
