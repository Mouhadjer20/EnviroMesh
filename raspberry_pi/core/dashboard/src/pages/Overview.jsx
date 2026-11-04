import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useData } from '../context/DataContext.jsx'
import { alertsFor, avg, eventsFromReadings, formatMetric, isDanger, isNum, isRecent, METRICS, hm, when } from '../lib.js'

const sensorCards = [
  { key: 'gas_ppm', title: 'Gaz (concentration)', unit: 'ppm', description: 'MQ-2 calibré uniquement' },
  { key: 'gas_adc_raw', title: 'Gaz (lecture brute)', unit: 'ADC', description: 'MQ-2 · valeur brute 0–4095' },
  { key: 'temperature_c', title: 'Température', unit: '°C', description: 'Température ambiante' },
  { key: 'humidity', title: 'Humidité', unit: '%', description: 'Humidité relative' },
  { key: 'water_leak', title: 'Fuite d’eau', unit: '', description: 'Détection binaire si configurée' },
  { key: 'water_adc_raw', title: 'Eau (lecture brute)', unit: 'ADC', description: 'Water Sensor · valeur brute 0–4095' },
  { key: 'pressure_hpa', title: 'Pression', unit: 'hPa', description: 'Pression atmosphérique' },
  { key: 'smoke_detected', title: 'Fumée', unit: '', description: 'Détection de fumée' },
  { key: 'motion_detected', title: 'Mouvement', unit: '', description: 'Détection de mouvement' },
]

function MetricCard({ metric, readings, trendReadings }) {
  const { key, title, unit, description } = metric
  const points = useMemo(() => trendReadings
    .filter(reading => isNum(reading.metrics?.[key]))
    .slice()
    .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
    .slice(-24)
    .map(reading => ({ t: Date.parse(reading.timestamp), value: reading.metrics[key] })), [trendReadings, key])
  const values = readings.map(reading => reading.metrics?.[key]).filter(value => value != null)
  let value = '—'
  let status = 'Aucune donnée récente'
  let statusKind = 'muted'

  if (values.length) {
    if (METRICS[key]?.binary) {
      const active = values.some(Boolean)
      value = key === 'motion_detected' ? (active ? 'Détecté' : 'Aucun') : (active ? 'Détectée' : 'Aucune')
      status = key === 'motion_detected' ? (active ? 'Mouvement signalé' : 'Aucun mouvement') : (active ? 'Alerte active' : 'Aucun signal')
      statusKind = active && key !== 'motion_detected' ? 'critical' : 'normal'
    } else {
      const average = avg(values)
      value = formatMetric(key, average)
      const danger = values.some(item => isDanger(key, item))
      status = danger ? 'Seuil d’alerte atteint' : METRICS[key]?.danger ? 'Dans la plage suivie' : 'Mesure reçue'
      statusKind = danger ? 'critical' : 'normal'
    }
  }

  return (
    <article className={`sensor-card ${statusKind}`}>
      <div className="sensor-card-top">
        <span className={`sensor-symbol sensor-${key}`} aria-hidden="true">{unit || (key === 'water_leak' ? 'H₂O' : key === 'smoke_detected' ? 'AIR' : 'PIR')}</span>
        <span className={`sensor-state ${statusKind}`}><i />{statusKind === 'critical' ? 'ALERTE' : statusKind === 'muted' ? 'INACTIF' : 'EN SUIVI'}</span>
      </div>
      <div className="sensor-value">{value}</div>
      <div className="sensor-label">{title}</div>
      <div className="sensor-card-bottom">
        <span>{description}</span>
        {points.length > 1 ? (
          <div className="sensor-sparkline" aria-label={`${points.length} dernières mesures de ${title}`}>
            <ResponsiveContainer width="100%" height={34}>
              <LineChart data={points}>
                <Line type="monotone" dataKey="value" stroke={statusKind === 'critical' ? 'var(--critical)' : 'var(--primary)'} strokeWidth={1.8} dot={false} />
                <Tooltip labelFormatter={when} formatter={v => [formatMetric(key, v), title]} contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)' }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : <span className="spark-empty">—</span>}
      </div>
    </article>
  )
}

export default function Overview() {
  const { devices, groups, latestBy, actives, readings, loading, zone } = useData()
  const [group, setGroup] = useState('all')
  const [stateFilter, setStateFilter] = useState('all')
  const zonesDevices = devices.filter(device => zone === 'all' || device.zone === zone)
  const visibleDevices = zonesDevices.filter(device => group === 'all' || device.group_code === group)
  const visibleIds = new Set(zonesDevices.map(device => device.device_id))
  const currentReadings = [...latestBy.values()].filter(reading => visibleIds.has(reading.device_id) && isRecent(reading))
  const onlineDevices = zonesDevices.filter(device => isRecent(latestBy.get(device.device_id)))
  const visibleAlerts = actives.filter(alert => visibleIds.has(alert.device))
  const filteredDevices = visibleDevices.filter(device => {
    const reading = latestBy.get(device.device_id)
    if (stateFilter === 'online') return isRecent(reading)
    if (stateFilter === 'alert') return isRecent(reading) && alertsFor(reading).length > 0
    return true
  })

  const chartReadings = useMemo(() => {
    const cutoff = Date.now() - 24 * 60 * 60 * 1000
    return readings
      .filter(reading => (zone === 'all' || reading.zone === zone) &&
        (group === 'all' || reading.group_code === group) &&
        Date.parse(reading.timestamp) >= cutoff)
      .slice()
      .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
  }, [readings, zone, group])
  const temperatureHumidity = chartReadings.filter(reading =>
    isNum(reading.metrics?.temperature_c) || isNum(reading.metrics?.humidity)
  ).map(reading => ({
    t: Date.parse(reading.timestamp),
    temperature: isNum(reading.metrics?.temperature_c) ? reading.metrics.temperature_c : null,
    humidity: isNum(reading.metrics?.humidity) ? reading.metrics.humidity : null,
  }))
  const gasReadings = chartReadings
    .filter(reading => isNum(reading.metrics?.gas_ppm))
    .map(reading => ({ t: Date.parse(reading.timestamp), value: reading.metrics.gas_ppm }))
  const sensorReadings = readings.filter(reading =>
    visibleIds.has(reading.device_id) && isRecent(latestBy.get(reading.device_id))
  )
  const events = useMemo(() => eventsFromReadings(readings)
    .filter(event => visibleIds.has(event.device))
    .slice(0, 5), [readings, visibleIds])
  const activeEventIds = new Set(visibleAlerts.map(alert => alert.cle))
  const deviceById = new Map(devices.map(device => [device.device_id, device]))
  const cardData = [
    { title: 'Appareils enregistrés', value: zonesDevices.length, detail: `${onlineDevices.length} actuellement en ligne`, icon: 'NODE', tone: 'teal' },
    { title: 'État du réseau', value: zonesDevices.length && onlineDevices.length === zonesDevices.length ? 'Opérationnel' : onlineDevices.length ? 'Partiel' : 'Hors ligne', detail: `${zonesDevices.length - onlineDevices.length} hors ligne`, icon: 'NET', tone: 'blue' },
    { title: 'Alertes actives', value: visibleAlerts.length.toString().padStart(2, '0'), detail: visibleAlerts.length ? 'Attention requise' : 'Aucune alerte active', icon: 'ALT', tone: visibleAlerts.length ? 'red' : 'green' },
    { title: 'Groupes suivis', value: new Set(zonesDevices.map(device => device.group_code).filter(Boolean)).size, detail: zone === 'all' ? 'Tous les secteurs' : zone, icon: 'GRP', tone: 'violet' },
  ]
  const filters = [
    { id: 'all', label: 'Tous', count: zonesDevices.length },
    { id: 'online', label: 'En ligne', count: onlineDevices.length },
    { id: 'alert', label: 'En alerte', count: zonesDevices.filter(device => isRecent(latestBy.get(device.device_id)) && alertsFor(latestBy.get(device.device_id)).length).length },
  ]
  const tooltipStyle = { background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 10, color: 'var(--text)' }

  return (
    <div className="overview-page">
      <header className="overview-heading">
        <div>
          <span className="eyebrow"><i /> APERÇU DU SYSTÈME</span>
          <h1>Vue d’ensemble</h1>
          <p>État environnemental actuel de vos appareils et zones surveillés.</p>
        </div>
        <span className="refresh-indicator"><i /> Actualisation automatique · 5 s</span>
      </header>

      <section className="kpi-grid" aria-label="Indicateurs du réseau">
        {cardData.map(card => (
          <article className={`kpi-card tone-${card.tone}`} key={card.title}>
            <div className="kpi-top"><span>{card.title}</span><b>{card.icon}</b></div>
            <strong>{card.value}</strong>
            <small>{card.detail}</small>
          </article>
        ))}
      </section>

      <section className="section-block" aria-labelledby="sensor-section-title">
        <div className="section-heading">
          <div><span className="eyebrow">MESURES ACTUELLES</span><h2 id="sensor-section-title">Surveillance environnementale</h2></div>
          <span className="section-meta">{currentReadings.length} appareils avec données récentes</span>
        </div>
        <div className="sensor-grid">
          {sensorCards.map(metric => <MetricCard key={metric.key} metric={metric} readings={currentReadings} trendReadings={sensorReadings} />)}
        </div>
        <p className="calibration-note">Les seuils d’alerte sont provisoires. Les valeurs du capteur MQ-2 ne représentent des ppm calibrés que si son étalonnage l’a confirmé.</p>
      </section>

      <section className="section-block" aria-labelledby="charts-section-title">
        <div className="section-heading">
          <div><span className="eyebrow">DONNÉES STOCKÉES</span><h2 id="charts-section-title">Tendances · dernières 24 heures</h2></div>
          <span className="section-meta">{chartReadings.length} mesures reçues</span>
        </div>
        <div className="chart-grid">
          <article className="chart-panel">
            <div className="panel-heading">
              <div><h3>Température & humidité</h3><span>Mesures combinées des appareils sélectionnés</span></div>
              <span className="chart-period-badge">24 H</span>
            </div>
            {temperatureHumidity.length > 1 ? (
              <div className="dashboard-chart">
                <ResponsiveContainer width="100%" height={245}>
                  <LineChart data={temperatureHumidity} margin={{ top: 10, right: 6, left: -18, bottom: 0 }}>
                    <CartesianGrid stroke="var(--border)" strokeDasharray="3 5" vertical={false} />
                    <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={hm} minTickGap={34} stroke="var(--muted)" fontSize={10} />
                    <YAxis yAxisId="temperature" stroke="var(--muted)" fontSize={10} width={44} />
                    <YAxis yAxisId="humidity" orientation="right" stroke="var(--muted)" fontSize={10} width={38} />
                    <Tooltip labelFormatter={when} formatter={(value, name) => [formatMetric(name === 'Température' ? 'temperature_c' : 'humidity', value), name]} contentStyle={tooltipStyle} />
                    <Line yAxisId="temperature" name="Température" type="monotone" dataKey="temperature" stroke="var(--primary)" strokeWidth={2} dot={false} connectNulls />
                    <Line yAxisId="humidity" name="Humidité" type="monotone" dataKey="humidity" stroke="var(--chart-blue)" strokeWidth={2} dot={false} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : <div className="chart-placeholder">{readings.length ? 'Pas assez de mesures sur les dernières 24 heures.' : 'En attente des premières mesures.'}</div>}
            <div className="chart-legend"><span><i className="legend-teal" /> Température · °C</span><span><i className="legend-blue" /> Humidité · %</span></div>
          </article>

          <article className="chart-panel">
            <div className="panel-heading">
              <div><h3>Surveillance du gaz</h3><span>Niveau reçu des capteurs · unité API : ppm</span></div>
              <span className="chart-period-badge">24 H</span>
            </div>
            {gasReadings.length > 1 ? (
              <div className="dashboard-chart">
                <ResponsiveContainer width="100%" height={245}>
                  <LineChart data={gasReadings} margin={{ top: 10, right: 6, left: -18, bottom: 0 }}>
                    <CartesianGrid stroke="var(--border)" strokeDasharray="3 5" vertical={false} />
                    <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={hm} minTickGap={34} stroke="var(--muted)" fontSize={10} />
                    <YAxis stroke="var(--muted)" fontSize={10} width={44} />
                    <Tooltip labelFormatter={when} formatter={value => [formatMetric('gas_ppm', value), 'Gaz']} contentStyle={tooltipStyle} />
                    <Line type="monotone" dataKey="value" stroke="var(--primary)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : <div className="chart-placeholder">{readings.length ? 'Pas assez de mesures de gaz sur les dernières 24 heures.' : 'En attente des premières mesures.'}</div>}
            <div className="chart-legend"><span><i className="legend-teal" /> Gaz · valeur reçue</span><span>{gasReadings.length} points</span></div>
          </article>
        </div>
      </section>

      <section className="lower-grid">
        <article className="panel alerts-panel">
          <div className="section-heading compact-heading">
            <div><span className="eyebrow">ÉVÉNEMENTS RÉCENTS</span><h2>Alertes récentes</h2></div>
            <Link to="/alerts" className="text-link">Tout afficher <span aria-hidden="true">→</span></Link>
          </div>
          {events.length ? (
            <ul className="recent-alerts">
              {events.map((event, index) => {
                const device = deviceById.get(event.device)
                const active = activeEventIds.has(`${event.device}|${event.id}`)
                return (
                  <li key={`${event.device}-${event.id}-${event.t}`} style={{ animationDelay: `${index * 60}ms` }}>
                    <span className={`alert-mark ${active ? 'critical' : 'resolved'}`}><i /></span>
                    <span className="alert-copy"><strong>{event.texte}</strong><small>{event.device} · {device?.zone || device?.group_code || 'Zone inconnue'}</small></span>
                    <span className={`alert-tag ${active ? 'critical' : ''}`}>{active ? 'Active' : 'Historique'}</span>
                    <time>{when(event.t)}</time>
                    <Link to={`/device/${event.device}`} className="alert-device-link" aria-label={`Détails de ${event.device}`}>↗</Link>
                  </li>
                )
              })}
            </ul>
          ) : <div className="empty-panel">{loading ? 'Chargement des événements…' : 'Aucun événement récent pour cette zone.'}</div>}
          <p className="data-source-note">Événements reconstruits à partir des mesures disponibles ; ils ne sont pas encore persistés dans une table d’alertes.</p>
        </article>

        <article className="panel fleet-panel" id="devices">
          <div className="section-heading compact-heading">
            <div><span className="eyebrow">APPAREILS CONNECTÉS</span><h2>Appareils & capteurs</h2></div>
            <span className="section-meta">{filteredDevices.length} / {zonesDevices.length}</span>
          </div>
          <div className="fleet-filter-row">
            <label>
              <span className="sr-only">Groupe</span>
              <select aria-label="Filtrer par groupe" value={group} onChange={event => setGroup(event.target.value)}>
                <option value="all">Tous les groupes</option>
                {groups.filter(item => zonesDevices.some(device => device.group_code === item.group_code))
                  .map(item => <option key={item.group_code} value={item.group_code}>{item.group_code}</option>)}
              </select>
            </label>
            <div className="filter-segment" role="group" aria-label="État des appareils">
              {filters.map(filter => (
                <button key={filter.id} type="button" className={stateFilter === filter.id ? 'active' : ''} aria-pressed={stateFilter === filter.id} onClick={() => setStateFilter(filter.id)}>
                  {filter.label}<span>{filter.count}</span>
                </button>
              ))}
            </div>
          </div>
          {filteredDevices.length ? (
            <div className="device-list">
              {filteredDevices.map((device, index) => {
                const reading = latestBy.get(device.device_id)
                const online = isRecent(reading)
                const metrics = Object.keys(reading?.metrics || {}).filter(key => reading.metrics[key] != null)
                return (
                  <Link className="device-row" key={device.device_id} to={`/device/${device.device_id}`} style={{ animationDelay: `${Math.min(index * 45, 270)}ms` }}>
                    <span className="device-state-dot"><i className={online ? 'online' : ''} /></span>
                    <span className="device-main"><strong>{device.device_id}</strong><small>{device.group_code || '—'} · {device.zone || 'Zone non définie'}</small></span>
                    <span className="device-sensors">{metrics.length} mesure{metrics.length > 1 ? 's' : ''}</span>
                    <span className={`device-status ${online ? 'online' : ''}`}>{online ? 'En ligne' : 'Hors ligne'}</span>
                    <span className="device-last-seen">{reading ? when(reading.timestamp) : 'Aucune mesure'}</span>
                    <span className="device-arrow" aria-hidden="true">→</span>
                  </Link>
                )
              })}
            </div>
          ) : <div className="empty-panel">{loading ? 'Chargement des appareils…' : 'Aucun appareil pour ces filtres.'}</div>}
        </article>
      </section>
    </div>
  )
}
