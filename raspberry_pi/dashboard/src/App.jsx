import { useEffect, useMemo, useState } from 'react'
import { Link, NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import { DataContext } from './context/DataContext.jsx'
import { useApi } from './hooks/useApi.js'
import { POLL_MS, alertsFor, isRecent, list, rows } from './lib.js'
import Overview from './pages/Overview.jsx'
import Device from './pages/Device.jsx'
import Alerts from './pages/Alerts.jsx'

const icons = {
  overview: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  live: <><path d="M3 12h3l3-7 5 14 3-7h4" /><circle cx="19" cy="12" r="2" /></>,
  alerts: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
  devices: <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M9 7h6m-6 4h6m-6 4h3" /></>,
  zones: <><path d="m3 7 6-4 6 4 6-4v14l-6 4-6-4-6 4z" /><path d="M9 3v14m6-10v14" /></>,
  analytics: <><path d="M3 3v18h18" /><path d="m7 14 4-4 4 3 6-7" /></>,
  actuator: <><circle cx="12" cy="12" r="3" /><path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.7a8 8 0 0 1-1.5.9l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.5-.9l-1.7.7-1.4-2.4 1.4-1.1a7 7 0 0 1 0-1.8l-1.4-1.1 1.4-2.4 1.7.7a8 8 0 0 1 1.5-.9l.3-1.8h2.8l.3 1.8a8 8 0 0 1 1.5.9l1.7-.7 1.4 2.4-1.4 1.1a7 7 0 0 1 0 1.8Z" /></>,
  users: <><path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="10" cy="7" r="4" /><path d="M20 21v-2a4 4 0 0 0-3-3.9m-1-11.8a4 4 0 0 1 0 7.8" /></>,
  security: <><path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z" /><path d="m9 12 2 2 4-4" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.7a8 8 0 0 1-1.5.9l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.5-.9l-1.7.7-1.4-2.4 1.4-1.1a7 7 0 0 1 0-1.8l-1.4-1.1 1.4-2.4 1.7.7a8 8 0 0 1 1.5-.9l.3-1.8h2.8l.3 1.8a8 8 0 0 1 1.5.9l1.7-.7 1.4 2.4-1.4 1.1a7 7 0 0 1 0 1.8Z" /></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
}

function Icon({ name }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true">{icons[name]}</svg>
}

function NavigationLink({ to, icon, children, badge, end = false }) {
  return (
    <NavLink className={({ isActive }) => `side-link${isActive ? ' active' : ''}`} to={to} end={end} title={children}>
      <Icon name={icon} />
      <span>{children}</span>
      {badge > 0 && <b className="side-badge">{badge}</b>}
    </NavLink>
  )
}

function ComingSoon({ icon, children }) {
  return (
    <span className="side-link disabled" aria-disabled="true" title={`${children} — bientôt disponible`}>
      <Icon name={icon} />
      <span>{children}</span>
      <small>À venir</small>
    </span>
  )
}

export default function App() {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('em-theme') || 'dark' } catch { return 'dark' }
  })
  const [zone, setZone] = useState('all')
  const [now, setNow] = useState(() => new Date())
  const navigate = useNavigate()
  const dev = useApi('/devices/', POLL_MS, list)
  const tel = useApi('/telemetry/?limit=500', POLL_MS, rows)
  const error = dev.error || tel.error

  useEffect(() => {
    try { localStorage.setItem('em-theme', theme) } catch {}
    const root = document.documentElement
    theme === 'auto' ? root.removeAttribute('data-theme') : root.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000)
    return () => window.clearInterval(timer)
  }, [])

  const latestBy = useMemo(() => {
    const latest = new Map()
    for (const reading of tel.data || []) {
      const current = latest.get(reading.device_id)
      if (!current || Date.parse(reading.timestamp) > Date.parse(current.timestamp)) latest.set(reading.device_id, reading)
    }
    return latest
  }, [tel.data])
  const devices = useMemo(() => {
    const byId = new Map((dev.data || []).filter(device => device.device_id).map(device => [device.device_id, device]))
    for (const [id, reading] of latestBy) {
      if (!byId.has(id)) byId.set(id, { device_id: id, group_code: reading.group_code, zone: reading.zone, sensors: [] })
    }
    return [...byId.values()].sort((a, b) => a.device_id.localeCompare(b.device_id))
  }, [dev.data, latestBy])
  const groups = useMemo(() => [...new Set(devices.map(device => device.group_code).filter(Boolean))]
    .sort().map(group_code => ({ group_code })), [devices])
  const zones = useMemo(() => [...new Set(devices.map(device => device.zone).filter(Boolean))].sort(), [devices])
  const actives = [...latestBy.values()].filter(isRecent)
    .flatMap(reading => alertsFor(reading).map(alert => ({ ...alert, device: reading.device_id, cle: `${reading.device_id}|${alert.id}` })))
  const nextTheme = { auto: 'light', light: 'dark', dark: 'auto' }
  const themeName = { auto: 'Auto', light: 'Clair', dark: 'Sombre' }

  const scrollToDevices = () => {
    navigate('/')
    window.setTimeout(() => document.getElementById('devices')?.scrollIntoView({ behavior: 'smooth' }), 80)
  }
  const connected = !error && !dev.loading && !tel.loading

  return (
    <DataContext.Provider value={{
      devices, groups, latestBy, actives, readings: tel.data || [],
      loading: dev.loading || tel.loading, zone, setZone,
    }}>
      <div className="app-shell">
        <aside className="sidebar">
          <Link className="brand" to="/" aria-label="EnviroMesh — Vue d’ensemble">
            <span className="brand-mark"><span /><span /><span /><span /></span>
            <span className="brand-copy"><strong>EnviroMesh</strong><small>ENVIRONMENTAL IOT</small></span>
          </Link>

          <nav className="side-navigation" aria-label="Navigation principale">
            <span className="side-heading">PRINCIPAL</span>
            <NavigationLink to="/" icon="overview" end>Vue d’ensemble</NavigationLink>
            <ComingSoon icon="live">Surveillance live</ComingSoon>

            <span className="side-heading">GESTION</span>
            <NavigationLink to="/alerts" icon="alerts" badge={actives.length}>Alertes & événements</NavigationLink>
            <button type="button" className="side-link side-button" onClick={scrollToDevices} title="Appareils & capteurs">
              <Icon name="devices" /><span>Appareils & capteurs</span>
            </button>
            <ComingSoon icon="zones">Zones & emplacements</ComingSoon>
            <ComingSoon icon="analytics">Analyses & historique</ComingSoon>
            <ComingSoon icon="actuator">Actionneurs</ComingSoon>

            <span className="side-heading">ADMINISTRATION</span>
            <ComingSoon icon="users">Utilisateurs & rôles</ComingSoon>
            <ComingSoon icon="security">Sécurité</ComingSoon>
            <ComingSoon icon="settings">Paramètres</ComingSoon>
          </nav>

          <div className="sidebar-footer">
            <span className={`connection-indicator ${connected ? 'online' : error ? 'offline' : ''}`} />
            <span><strong>{connected ? 'API connectée' : error ? 'API indisponible' : 'Connexion…'}</strong><small>Authentification non configurée</small></span>
          </div>
        </aside>

        <main className="app-main">
          <header className="topbar">
            <div className="topbar-date">
              <span className="topbar-eyebrow">ENVIRONNEMENT DE SURVEILLANCE</span>
              <strong>{now.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</strong>
            </div>
            <div className="topbar-actions">
              <label className="zone-picker">
                <span>Zone</span>
                <select aria-label="Filtrer par zone" value={zone} onChange={event => setZone(event.target.value)}>
                  <option value="all">Toutes les zones</option>
                  {zones.map(item => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <span className={`server-status ${connected ? 'online' : error ? 'offline' : ''}`} role="status">
                <i />{connected ? 'Serveur en ligne' : error ? 'Serveur indisponible' : 'Connexion…'}
              </span>
              <Link className="icon-action notification-action" to="/alerts" aria-label={`Alertes${actives.length ? `, ${actives.length} actives` : ''}`} title="Alertes">
                <Icon name="bell" />{actives.length > 0 && <span>{actives.length}</span>}
              </Link>
              <button
                type="button"
                className="icon-action theme-action"
                onClick={() => setTheme(nextTheme[theme])}
                aria-label={`Thème actuel : ${themeName[theme]}. Cliquer pour changer.`}
                title={`Thème ${themeName[theme]}`}
              >
                {theme === 'dark'
                  ? <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" /></svg>
                  : <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.2 15.4A8.5 8.5 0 0 1 8.6 3.8 8.5 8.5 0 1 0 20.2 15.4Z" /></svg>}
              </button>
            </div>
          </header>

          <div className="workspace">
            {error && (
              <div className="api-error" role="alert">
                <strong>{error}</strong>
                <span>Vérifie que la pile Docker tourne (<code>docker compose ps</code>) et que la base est initialisée.</span>
              </div>
            )}
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/device/:id" element={<Device />} />
              <Route path="/alerts" element={<Alerts />} />
              <Route path="*" element={<Overview />} />
            </Routes>
            <footer className="workspace-footer">EnviroMesh · Les mesures affichées proviennent de l’API du projet.</footer>
          </div>
        </main>
      </div>
    </DataContext.Provider>
  )
}
