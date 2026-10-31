import test from 'node:test'
import assert from 'node:assert/strict'
import { hexlify, toUtf8Bytes } from 'ethers'
import { sendCommitment, INTEGRITY_SINK, connectWallet } from '../../src/components/integrity/wallet.js'

const address = '0x' + '1'.repeat(40)
const value = { chain_id: 84532, sha256: 'a'.repeat(64), current_sha256: 'a'.repeat(64), data: hexlify(toUtf8Bytes('revelio:image:v1:sha256:' + 'a'.repeat(64))) }
const signer = (sendTransaction, account = address, chainId = 84532n) => ({ getAddress: async () => account, provider: { getNetwork: async () => ({ chainId }) }, sendTransaction })

test('reproduces MetaMask -32602 for self-data and sends new commitment to sink', async () => {
  let sent
  const wallet = signer(async tx => {
    if (tx.to.toLowerCase() === address && tx.data) throw Object.assign(new Error('External transactions to internal accounts cannot include data.'), { code: -32602 })
    sent = tx
    return { hash: '0x'+'a'.repeat(64) }
  })
  await assert.rejects(wallet.sendTransaction({ to: address, value: 0n, data: value.data }), { code: -32602 })
  await sendCommitment(wallet, value)
  assert.deepEqual(sent, { from: address, to: INTEGRITY_SINK, value: 0n, data: value.data, chainId: 84532 })
  assert.notEqual(sent.to.toLowerCase(), sent.from.toLowerCase())
})

test('blocks wrong chain, sink sender, changed bytes and malformed commitments before sending', async () => {
  const never = () => assert.fail('Must not send a transaction')
  await assert.rejects(sendCommitment(signer(never, address, 1n), value), /Base Sepolia/)
  await assert.rejects(sendCommitment(signer(never, INTEGRITY_SINK), value), /sender must differ/)
  for (const invalid of [{ ...value, chain_id: 1 }, { ...value, current_sha256: 'b'.repeat(64) }, { ...value, data: '0x1234' }]) {
    await assert.rejects(sendCommitment(signer(never), invalid), /Invalid image commitment/)
  }
})

test('wallet rejection propagates without resubmitting', async () => {
  let calls = 0
  await assert.rejects(sendCommitment(signer(async () => { calls++; throw Object.assign(new Error('Rejected'), { code: 4001 }) }), value), { code: 4001 })
  assert.equal(calls, 1)
})

test('network switch must finish on Base Sepolia before obtaining a signer', async () => {
  const calls = []
  await assert.rejects(connectWallet({ isMetaMask: true, request: async ({ method }) => { calls.push(method); return method === 'eth_chainId' ? '0x1' : [] } }), /Base Sepolia/)
  assert.deepEqual(calls, ['eth_requestAccounts', 'eth_chainId', 'wallet_switchEthereumChain', 'eth_chainId'])
})
