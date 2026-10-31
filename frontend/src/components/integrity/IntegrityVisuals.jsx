// Visual summaries of an integrity result: the verification chain, a byte-level
// fingerprint comparison and the on-chain record. Display only; every value shown
// comes from the backend's independent check, never from the wallet.

const STEPS = [
  { key: 'file', label: 'Saved image', hint: 'Original file bytes on disk' },
  { key: 'hash', label: 'Fingerprint', hint: 'SHA-256 matches the revision' },
  { key: 'commit', label: 'Commitment', hint: 'Bound to this revision ID' },
  { key: 'tx', label: 'Transaction', hint: 'Sender, sink, zero value' },
  { key: 'receipt', label: 'Receipt', hint: 'Executed successfully' },
  { key: 'block', label: 'Block', hint: 'Canonical on Base Sepolia' },
]

// Backend result code → [step index, state]. Steps before it passed; steps after it were not reached.
const CODE_STEP = {
  IMAGE_HASH_MISMATCH: [1, 'fail'],
  NOT_REGISTERED: [3, 'idle'],
  TRANSACTION_NOT_VISIBLE: [3, 'pending'],
  TRANSACTION_IDENTITY_MISMATCH: [3, 'fail'],
  SENDER_MISMATCH: [3, 'fail'],
  NONZERO_VALUE: [3, 'fail'],
  RECIPIENT_MISMATCH: [3, 'fail'],
  COMMITMENT_MISMATCH: [2, 'fail'],
  EXECUTED_COMMITMENT_MISMATCH: [2, 'fail'],
  RECEIPT_PENDING: [4, 'pending'],
  RECEIPT_IDENTITY_MISMATCH: [4, 'fail'],
  TRANSACTION_REVERTED: [4, 'fail'],
  BLOCK_PENDING: [5, 'pending'],
  BLOCK_NOT_CANONICAL: [5, 'pending'],
  VERIFIED: [6, 'ok'],
}

const STATE_TEXT = { ok: 'passed', pending: 'waiting', fail: 'failed', error: 'not checked', idle: 'not reached' }

function chainStates(result) {
  if (!result) return STEPS.map(() => 'idle')
  // RPC problems stop the check at the first on-chain step without judging the transaction.
  const [at, state] = CODE_STEP[result.code] || (result.code?.startsWith('RPC_') ? [3, 'error'] : [0, 'idle'])
  return STEPS.map((_, i) => (i < at ? 'ok' : i === at ? state : 'idle'))
}

export function IntegrityChain({ result, loading }) {
  const states = chainStates(result)
  return (
    <ol className={`wt-int-chain ${loading ? 'is-loading' : ''}`} aria-label="Verification chain">
      {STEPS.map((step, i) => (
        <li key={step.key} className={`wt-int-step is-${states[i]}`}>
          <span className="wt-int-step__node" aria-hidden="true">
            {states[i] === 'ok' ? '✓' : states[i] === 'fail' ? '✕' : states[i] === 'pending' ? '…' : states[i] === 'error' ? '!' : i + 1}
          </span>
          <span className="wt-int-step__label">{step.label}</span>
          <span className="wt-int-step__hint">{step.hint}</span>
          <span className="sr-only">: {STATE_TEXT[states[i]]}</span>
        </li>
      ))}
    </ol>
  )
}

const bytes = (hex) => (hex && /^[0-9a-f]{64}$/i.test(hex) ? hex.toLowerCase().match(/../g) : null)

// Each byte becomes a coloured cell, so a single changed byte is visible at a glance.
function Strip({ label, cells, diff }) {
  return (
    <div className="wt-int-strip">
      <span className="wt-int-strip__label">{label}</span>
      <span className="wt-int-strip__cells" aria-hidden="true">
        {cells.map((b, i) => (
          <i key={i} className={diff[i] ? 'is-diff' : ''}
            style={{ '--h': `${Math.round((parseInt(b, 16) / 255) * 300)}deg`, '--l': `${38 + (parseInt(b, 16) % 5) * 6}%` }} />
        ))}
      </span>
      <code className="wt-int-strip__hex">
        {cells.map((b, i) => <span key={i} className={diff[i] ? 'is-diff' : ''}>{b}</span>)}
      </code>
    </div>
  )
}

export function HashFingerprint({ original, current }) {
  const a = bytes(original)
  const b = bytes(current)
  if (!a || !b) return null
  const diff = a.map((x, i) => x !== b[i])
  const changed = diff.filter(Boolean).length
  return (
    <figure className={`wt-int-print ${changed ? 'is-changed' : 'is-same'}`}>
      <figcaption>
        <span>Image fingerprint (SHA-256)</span>
        <b>{changed ? `${changed} of 32 bytes differ` : 'All 32 bytes match'}</b>
      </figcaption>
      <Strip label="Original" cells={a} diff={diff} />
      <Strip label="Current" cells={b} diff={diff} />
      {changed > 0 && <p className="wt-int-print__note">Changing even one byte of the image changes almost the whole fingerprint, so any edit is detectable.</p>}
    </figure>
  )
}

const short = (v) => (v ? `${v.slice(0, 8)}…${v.slice(-6)}` : '—')

export function ChainRecord({ result, txHash, sink }) {
  if (!txHash) return null
  const mode = { direct: 'Direct transaction', legacy_direct: 'Legacy self-transaction', wallet_delegation_trace: 'Wallet delegation (traced)' }[result?.verification_mode]
  const rows = [
    ['Network', 'Base Sepolia · 84532'],
    ['Block', result?.block_number != null
      ? <a href={`https://sepolia.basescan.org/block/${result.block_number}`} target="_blank" rel="noreferrer">#{result.block_number.toLocaleString()}</a>
      : 'Not confirmed yet'],
    ['Block time', result?.block_time ? new Date(result.block_time * 1000).toLocaleString() : '—'],
    ['Wallet', <span className="mono" title={result?.expected_sender || ''}>{short(result?.expected_sender)}</span>],
    ['Recipient', <span className="mono" title={sink}>{short(sink)} (sink)</span>],
    ['Value', '0 ETH'],
    ['Verification', mode || '—'],
  ]
  return (
    <dl className="wt-int-record">
      {rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
    </dl>
  )
}
