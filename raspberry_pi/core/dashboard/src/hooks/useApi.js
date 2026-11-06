import { useEffect, useState } from 'react'
import { POLL_MS } from '../lib.js'
import { apiRequest } from '../api.js'

export function useApi(path, every = POLL_MS, select = x => x) {
  const [s, setS] = useState({ data: null, error: '', loading: true })
  useEffect(() => {
    if (!path) {
      setS({ data: null, error: '', loading: false })
      return
    }
    let stop = false
    setS({ data: null, error: '', loading: true })
    const go = async () => {
      try {
        const d = select(await apiRequest(path))
        if (!stop) setS({ data: d, error: '', loading: false })
      } catch (e) { if (!stop) setS(p => ({ ...p, error: e.message || 'API indisponible', loading: false })) }
    }
    go()
    const id = setInterval(go, every)
    return () => { stop = true; clearInterval(id) }
  }, [path, every])
  return s
}
