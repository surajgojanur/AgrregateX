/** Abort superseded dashboard fetches and ignore any late completion. */
export function createDashboardRequestGate() {
  let sequence = 0
  let current = null

  return {
    begin(key) {
      if (current?.pending && current.key === key) return null
      if (current?.pending) {
        current.controller.abort()
        current.pending = false
      }
      const ticket = {
        id: ++sequence,
        key,
        controller: new AbortController(),
        pending: true,
      }
      current = ticket
      return ticket
    },
    isCurrent(ticket) {
      return Boolean(ticket && current === ticket && ticket.pending && !ticket.controller.signal.aborted)
    },
    finish(ticket) {
      if (current !== ticket) return false
      ticket.pending = false
      current = null
      return true
    },
    cancel(key) {
      if (!current?.pending || current.key !== key) return false
      current.controller.abort()
      current.pending = false
      current = null
      sequence += 1
      return true
    },
    get pending() {
      return Boolean(current?.pending)
    },
    get currentKey() {
      return current?.key ?? null
    },
  }
}
