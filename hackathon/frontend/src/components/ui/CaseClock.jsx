import { useEffect, useState } from 'react'

const pad = (n) => String(n).padStart(2, '0')

const CaseClock = () => {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const time = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
  return (
    <div className="clock mono" aria-label={`Local time ${time}`}>
      <span className="clock__date">{date}</span>
      <time dateTime={now.toISOString()}>{time}</time>
    </div>
  )
}

export default CaseClock
