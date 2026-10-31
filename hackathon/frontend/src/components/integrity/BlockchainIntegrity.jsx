import { useEffect, useState } from 'react'
import { witness } from '../../api/witnesstrace'
import { connectWallet, sendCommitment, INTEGRITY_SINK } from './wallet'
import { ChainRecord, HashFingerprint, IntegrityChain } from './IntegrityVisuals'

export default function BlockchainIntegrity({ caseId, versionId }) {
  const [result, setResult] = useState(null)
  const [address, setAddress] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState(null)
  const [submittedSender, setSubmittedSender] = useState(null)
  const path = `/api/cases/${caseId}/versions/${versionId}/integrity`
  useEffect(() => {
    let active = true
    witness.operation(path).then(value => { if (active) setResult(value) }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [path])
  useEffect(() => {
    const reset = () => setAddress('')
    window.ethereum?.on?.('accountsChanged', reset)
    window.ethereum?.on?.('chainChanged', reset)
    return () => {
      window.ethereum?.removeListener?.('accountsChanged', reset)
      window.ethereum?.removeListener?.('chainChanged', reset)
    }
  }, [])
  const run = async action => {
    setBusy(true); setError('')
    try { await action() } catch (e) { setError(e.code === 'ACTION_REJECTED' || e.code === 4001 ? 'MetaMask request declined. No registration completed.' : e.shortMessage || e.message) }
    finally { setBusy(false) }
  }
  const verify = async () => {
    const value = submitted ? await witness.operation(path, { tx_hash: submitted, sender: submittedSender }) : await witness.operation(path)
    setResult(value)
  }
  const register = async () => {
    const wallet = await connectWallet()
    setAddress(wallet.address)
    const value = await witness.operation(path)
    setResult(value)
    if (value.status !== 'NOT REGISTERED') throw new Error('Verify the existing revision registration before proceeding.')
    const tx = await sendCommitment(wallet.signer, value) // MetaMask explicitly asks the user to approve.
    setSubmitted(tx.hash)
    setSubmittedSender(tx.from)
    setResult({ ...value, tx_hash: tx.hash, status: 'PENDING', message: 'Waiting for a successful transaction receipt.' })
    // Persist before waiting so reloads can recover. The backend independently verifies the receipt.
    const registered = await witness.operation(path, { tx_hash: tx.hash, sender: tx.from })
    setResult(registered)
    if (registered.status !== 'PENDING') return
    let receipt
    try { receipt = await tx.wait(1, 120000) } catch (e) {
      if (e.code === 'TRANSACTION_REPLACED' && !e.cancelled && e.replacement?.data === value.data) {
        throw new Error(`Transaction replaced (${e.replacement.hash}). Original registration remains pending; investigate in BaseScan.`)
      }
      throw e
    }
    if (!receipt || receipt.status !== 1) throw new Error('Transaction has not succeeded. Use Verify Integrity to check again.')
    setResult(await witness.operation(path, { tx_hash: tx.hash, sender: tx.from }))
  }
  const txHash = submitted || result?.tx_hash
  const status = error ? 'ERROR' : result?.status || 'PENDING'
  return <section className="panel"><div className="panel__head"><h2 className="panel__title">Blockchain Integrity</h2></div><div className="panel__body wt-fields">
    <div className={`wt-int-status is-${status.toLowerCase().replace(' ', '-')}`} role="status" aria-live="polite">
      <strong>{status}</strong>
      <span>{error || result?.message || 'Loading integrity record…'}</span>
    </div>
    <div className="wt-int">
      <IntegrityChain result={result} loading={!result || busy} />
      {result && <HashFingerprint original={result.sha256} current={result.current_sha256} />}
      <ChainRecord result={result} txHash={txHash} sink={INTEGRITY_SINK} />
    </div>
    <p className="wt-id faint">Base Sepolia testnet · 84532. Registration sends a zero-value transaction to the fixed public sink {INTEGRITY_SINK} and uses test ETH for gas. Only a versioned hash commitment is public; image bytes and testimony stay local.</p>
    <div className="wt-int-actions">
      <button className="btn" disabled={busy} onClick={() => run(async () => { const wallet = await connectWallet(); setAddress(wallet.address) })}>Connect MetaMask</button>
      <button className="btn btn--primary" disabled={busy || !result || result.status !== 'NOT REGISTERED' || !!submitted} onClick={() => run(register)}>Register on Blockchain</button>
      <button className="btn" disabled={busy} onClick={() => run(verify)}>Verify Integrity</button>
    </div>
    {address && <p className="mono wt-id">Wallet: {address}</p>}
    {result?.code && <p className="mono wt-id">Diagnostic: {result.code}{result.retryable ? ' · Safe to retry Verify Integrity; do not register again.' : ''}</p>}
    {result?.verification_mode === 'wallet_delegation_trace' && <p>Verified through the wallet’s delegated execution trace, including the zero-value call to the fixed sink.</p>}
    {busy && <p>Waiting for MetaMask or transaction verification…</p>}
    {txHash && <a className="wt-id" href={`https://sepolia.basescan.org/tx/${txHash}`} target="_blank" rel="noreferrer">View transaction on BaseScan: {txHash}</a>}
  </div></section>
}
