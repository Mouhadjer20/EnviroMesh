export const API = '/api'
export const POLL_MS = 5000
export const ONLINE_MS = 60000
// Seuils d'alerte : gaz > 2000 ppm (README). La température max est un choix provisoire.
export const SEUILS = { gas_ppm: 2000, temperature_c: 50 }

// Noms de métriques réellement stockés dans sensor_telemetry (vérifiés en base)
export const METRICS = {
  gas_ppm: { label: 'Gaz', unit: 'ppm', danger: SEUILS.gas_ppm },
  gas_adc_raw: { label: 'Gaz (lecture brute)', unit: 'ADC' },
  water_adc_raw: { label: 'Eau (lecture brute)', unit: 'ADC' },
  temperature_c: { label: 'Température', unit: '°C', danger: SEUILS.temperature_c },
  humidity: { label: 'Humidité', unit: '%' },
  pressure_hpa: { label: 'Pression', unit: 'hPa' },
  water_leak: { label: 'Fuite d’eau', binary: true },
  smoke_detected: { label: 'Fumée', binary: true },
  motion_detected: { label: 'Mouvement', binary: true },
}
export const PLAGES = [
  { id: '1h', nom: '1 h', ms: 3600e3 }, { id: '24h', nom: '24 h', ms: 86400e3 },
  { id: '7j', nom: '7 j', ms: 604800e3 }, { id: 'tout', nom: 'Tout', ms: Infinity },
]

export const isNum = v => typeof v === 'number' && Number.isFinite(v)
export const avg = a => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null)
export const fix = (v, d = 1) => (v == null ? '—' : Number(v).toFixed(d))
export const label = k => METRICS[k]?.label || k.replaceAll('_', ' ').replace(/^\w/, c => c.toUpperCase())
export const isRecent = r => !!r && Date.now() - new Date(r.timestamp).getTime() <= ONLINE_MS

export function formatMetric(k, v) {
  if (v == null) return '—'
  const m = METRICS[k]
  if (m?.binary) return v ? 'Oui' : 'Non'
  const s = isNum(v) ? (Number.isInteger(v) ? String(v) : v.toFixed(1)) : String(v)
  return m?.unit ? `${s} ${m.unit}` : s
}

export function isDanger(k, v) {
  if (k === 'water_leak' || k === 'smoke_detected') return !!v
  const d = METRICS[k]?.danger
  return d != null && isNum(v) && v >= d
}

export function alertsFor(r) {
  const m = r?.metrics || {}, a = []
  if (m.water_leak) a.push({ id: 'eau', texte: 'Fuite d’eau détectée' })
  if (m.smoke_detected) a.push({ id: 'fumee', texte: 'Fumée détectée' })
  if (isDanger('gas_ppm', m.gas_ppm)) a.push({ id: 'gaz', texte: `Gaz élevé (${Math.round(m.gas_ppm)} ppm)` })
  if (isDanger('temperature_c', m.temperature_c)) a.push({ id: 'temp', texte: `Température élevée (${m.temperature_c.toFixed(1)} °C)` })
  return a
}

// Transforme un historique (le plus récent en premier) en événements : une ligne à chaque DÉBUT d'alerte
export function eventsFromReadings(readings) {
  const prev = new Map(), out = []
  for (const r of [...readings].reverse()) {
    const before = prev.get(r.device_id) || new Set(), cur = new Set()
    for (const a of alertsFor(r)) {
      cur.add(a.id)
      if (!before.has(a.id)) out.push({ t: r.timestamp, device: r.device_id, id: a.id, texte: a.texte })
    }
    prev.set(r.device_id, cur)
  }
  return out.reverse()
}

export function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = document.createElement('a')
  a.href = url; a.download = name; a.click()
  URL.revokeObjectURL(url)
}

export function toCsv(rows) {
  const keys = [...new Set(rows.flatMap(r => Object.keys(r.metrics || {})))]
  const q = v => `"${String(v ?? '').replaceAll('"', '""')}"`
  return '\ufeff' + [['timestamp', 'device_id', 'group_code', ...keys].join(','),
    ...rows.map(r => [r.timestamp, r.device_id, r.group_code, ...keys.map(k => r.metrics?.[k])].map(q).join(','))].join('\n')
}

export const when = t => new Date(t).toLocaleString('fr-FR')
export const hm = t => new Date(t).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })

// --- Tolérance aux variantes de réponse de l'API ---
export const list = d => (Array.isArray(d) ? d : d?.items || d?.data || d?.results || [])
export function normalize(r) {
  let m = r.metrics ?? r.data ?? {}
  if (typeof m === 'string') { try { m = JSON.parse(m) } catch { m = {} } }
  const meta = r.metadata && typeof r.metadata === 'object' ? r.metadata : {}
  return { ...r, metrics: m, timestamp: r.timestamp || r.time || r.received_at,
    group_code: r.group_code || meta.group_code, rssi: r.rssi ?? meta.rssi_dbm ?? meta.rssi }
}
// Mesures normalisées, la plus récente en premier
export const rows = d => list(d).map(normalize).filter(r => r.device_id && r.timestamp)
  .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))
