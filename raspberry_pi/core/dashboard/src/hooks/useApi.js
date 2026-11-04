import { useEffect, useState } from 'react'
import { API, POLL_MS } from '../lib.js'

export function useApi(path, every = POLL_MS, select = x => x) {
  const [s, setS] = useState({ data: null, error: '', loading: true })
  useEffect(() => {
    if (!path) return
    let stop = false
    const go = async () => {
      try {
        const r = await fetch(API + path, { cache: 'no-store' })
        if (!r.ok) throw new Error(`Erreur API (${r.status}) sur ${path}`)
        const d = select(await r.json())
        if (!stop) setS({ data: d, error: '', loading: false })
      } catch (e) { if (!stop) setS(p => ({ ...p, error: e.message || 'API indisponible', loading: false })) }
    }
    go()
    const id = setInterval(go, every)
    return () => { stop = true; clearInterval(id) }
  }, [path, every])
  return s
}
