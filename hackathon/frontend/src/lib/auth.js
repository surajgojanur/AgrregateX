// Where to go after logging in. Only workspace paths are accepted, so a crafted
// ?next= link can never send someone to another site.
export function safeNext(next) {
  return typeof next === 'string' && /^\/app(?:[/?#]|$)/.test(next) ? next : '/app'
}
