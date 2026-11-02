import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Chart from '../components/Chart.jsx'
import { useData } from '../context/DataContext.jsx'
import { useApi } from '../hooks/useApi.js'
import { METRICS, PLAGES, POLL_MS, rows as toRows, alertsFor, avg, download, eventsFromReadings, formatMetric, isDanger, isNum, isRecent, label, toCsv, when } from '../lib.js'

export default function Device() {
  const { id } = useParams()
  const { devices, latestBy } = useData()
  const hist = useApi(`/telemetry/?device_id=${encodeURIComponent(id)}&limit=1000`, POLL_MS, d => toRows(d).filter(r => r.device_id === id))
  const [plage, setPlage] = useState('24h')
  const [metric, setMetric] = useState('')
  const device = devices.find(d => d.device_id === id)
  const latest = latestBy.get(id)
  const ms = PLAGES.find(p => p.id === plage).ms
  const rows = useMemo(() => (hist.data || []).filter(r => Date.now() - new Date(r.timestamp).getTime() <= ms), [hist.data, plage])
  const keys = [...new Set((hist.data || []).flatMap(r => Object.keys(r.metrics || {})))].sort()
  const sel = keys.includes(metric) ? metric : keys[0] || ''
  const points = rows.filter(r => isNum(r.metrics?.[sel])).map(r => ({ t: Date.parse(r.timestamp), v: r.metrics[sel] })).reverse()
  const nums = points.map(p => p.v)
  const events = useMemo(() => eventsFromReadings(rows), [rows])
  const on = isRecent(latest)

  return (
    <>
      <Link to="/" className="retour">← Tous les nœuds</Link>
      <section className="bloc">
        <div className="node-heading">
          <div><h2>{id}</h2><p className="soustitre">{device ? `${device.group_code || '—'} · ${device.zone || 'Zone non définie'}` : 'Nœud inconnu du registre'}</p></div>
          <span className={`node-status ${on ? 'online' : ''}`}>{on ? 'En ligne' : 'Hors ligne'}</span>
        </div>
        {on && alertsFor(latest).length > 0 && <div className="alert-badges">{alertsFor(latest).map(a => <span key={a.id}>{a.texte}</span>)}</div>}
        <dl className="fiche">
          <div><dt>Dernière mesure</dt><dd>{latest ? when(latest.timestamp) : '—'}</dd></div>
          <div><dt>Protocole</dt><dd>{latest?.protocol || '—'}</dd></div>
          <div><dt>Signal (RSSI)</dt><dd>{latest?.rssi != null ? `${latest.rssi} dBm` : '—'}</dd></div>
          <div><dt>Position GPS</dt><dd>{device?.latitude != null && device?.longitude != null ? `${device.latitude}, ${device.longitude}` : '—'}</dd></div>
        </dl>
        <div className="sensor-tags">{(device?.sensors || []).map(s => <span key={s.name} title={s.status}>{s.name} · {s.status}</span>)}</div>
        {latest && (
          <div className="node-metrics">
            {Object.entries(latest.metrics || {}).map(([k, v]) => (
              <div key={k} className={`node-metric ${on && isDanger(k, v) ? 'danger' : ''}`}><span>{label(k)}</span><strong>{formatMetric(k, v)}</strong></div>
            ))}
          </div>
        )}
      </section>

      <section className="histo">
        <div className="histo-tete">
          <h2>Historique</h2>
          <div className="controles">
            <label>Mesure
              <select value={sel} onChange={e => setMetric(e.target.value)}>{keys.map(k => <option key={k} value={k}>{label(k)}</option>)}</select>
            </label>
            <div className="plages" role="group" aria-label="Période">
              {PLAGES.map(p => <button key={p.id} className={plage === p.id ? 'actif' : ''} onClick={() => setPlage(p.id)}>{p.nom}</button>)}
            </div>
          </div>
        </div>
        {hist.error && <p className="vide">{hist.error}</p>}
        <Chart points={points} metric={sel} />
        {nums.length > 0 && !METRICS[sel]?.binary && (
          <dl className="stats">
            <div><dt>Min</dt><dd>{formatMetric(sel, Math.min(...nums))}</dd></div>
            <div><dt>Moyenne</dt><dd>{formatMetric(sel, avg(nums))}</dd></div>
            <div><dt>Max</dt><dd>{formatMetric(sel, Math.max(...nums))}</dd></div>
            <div><dt>Mesures</dt><dd>{nums.length}</dd></div>
          </dl>
        )}
        <div className="export">
          <button disabled={!rows.length} onClick={() => download(`${id}-telemetry.csv`, toCsv(rows), 'text/csv;charset=utf-8')}>Exporter en CSV</button>
          <button disabled={!rows.length} onClick={() => download(`${id}-telemetry.json`, JSON.stringify(rows, null, 2), 'application/json')}>Exporter en JSON</button>
          <span>{rows.length} mesures sur la période</span>
        </div>
      </section>

      <section className="journal">
        <h2>Alertes de ce nœud</h2>
        {events.length
          ? <ul>{events.slice(0, 15).map((e, i) => <li key={i}><time>{when(e.t)}</time>{e.texte}</li>)}</ul>
          : <p className="vide">Aucune alerte sur cette période.</p>}
      </section>
    </>
  )
}
