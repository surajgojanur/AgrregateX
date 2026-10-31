import { BrowserProvider, hexlify, toUtf8Bytes } from 'ethers'

export const INTEGRITY_SINK = '0x000000000000000000000000000000000000dEaD'

export async function connectWallet(ethereum = window.ethereum) {
  if (!ethereum?.isMetaMask) throw new Error('MetaMask is unavailable. Open this app in the browser with MetaMask installed.')
  await ethereum.request({ method: 'eth_requestAccounts' })
  if (BigInt(await ethereum.request({ method: 'eth_chainId' })) !== 84532n) {
    await ethereum.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: '0x14a34' }] })
  }
  if (BigInt(await ethereum.request({ method: 'eth_chainId' })) !== 84532n) throw new Error('Base Sepolia is required.')
  const provider = new BrowserProvider(ethereum)
  const signer = await provider.getSigner()
  return { signer, address: await signer.getAddress() }
}

export async function sendCommitment(signer, value) {
  if (value.chain_id !== 84532 || value.sha256 !== value.current_sha256 || !new RegExp('^0x' + hexlify(toUtf8Bytes('revelio:image:v1:sha256:')).slice(2) + '(?:3[0-9]|6[1-6]){64}$').test(value.data)) throw new Error('Invalid image commitment or modified image.')
  if ((await signer.provider.getNetwork()).chainId !== 84532n) throw new Error('Switch MetaMask to Base Sepolia.')
  const from = await signer.getAddress()
  if (from.toLowerCase() === INTEGRITY_SINK.toLowerCase()) throw new Error('The sender must differ from the integrity sink.')
  return signer.sendTransaction({ from, to: INTEGRITY_SINK, value: 0n, data: value.data, chainId: 84532 })
}
