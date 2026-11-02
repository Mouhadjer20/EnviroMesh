import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../context/DataContext.jsx'
import { useApi } from '../hooks/useApi.js'
import { eventsFromReadings, rows, when } from '../lib.js'

export default function Alerts() {
  const { actives } = useData()
  const h = useApi('/telemetry/?limit=2000', 15000, rows)
  const events = useMemo(() => eventsFromReadings(h.data || []), [h.data])
  return (
    <>
      <section className={`statut ${actives.length ? 'alerte' : 'ok'}`} role="status">
        <strong>{actives.length ? `${actives.length} alerte${actives.length > 1 ? 's' : ''} active${actives.length > 1 ? 's' : ''}` : 'Aucune alerte active'}</strong>
        {actives.map(a => <span key={a.cle}>{a.device} — {a.texte}</span>)}
      </section>
      <section className="bloc">
        <h2>Historique des alertes</h2>
        <p className="soustitre">Calculé à partir des 2000 dernières mesures. Il sera remplacé par la table d’alertes du backend.</p>
        {h.error && <p className="vide">{h.error}</p>}
        {events.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Date</th><th>Nœud</th><th>Alerte</th></tr></thead>
              <tbody>{events.slice(0, 100).map((e, i) => (
                <tr key={i}><td>{when(e.t)}</td><td><Link to={`/device/${e.device}`}>{e.device}</Link></td><td>{e.texte}</td></tr>
              ))}</tbody>
            </table>
          </div>
        ) : <p className="vide">Aucune alerte dans l’historique.</p>}
      </section>
    </>
  )
}
