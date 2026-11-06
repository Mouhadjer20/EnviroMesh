import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../api.js'
import { useData } from '../context/DataContext.jsx'

export default function GroupManagement() {
  const { devices } = useData()
  const [groups, setGroups] = useState([])
  const [users, setUsers] = useState([])
  const [description, setDescription] = useState('')
  const [groupCode, setGroupCode] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [groupRows, userRows] = await Promise.all([apiRequest('/groups/'), apiRequest('/users/')])
      setGroups(groupRows)
      setUsers(userRows)
      setError('')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { load() }, [load])

  async function createGroup(event) {
    event.preventDefault()
    setError('')
    setNotice('')
    setSaving(true)
    try {
      await apiRequest('/groups/', { method: 'POST', body: { group_code: groupCode, description: description.trim() } })
      setGroupCode('')
      setDescription('')
      setNotice('Groupe créé.')
      await load()
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSaving(false)
    }
  }

  async function updateDescription(group) {
    const next = window.prompt(`Description du groupe ${group.group_code}`, group.description || '')
    if (next === null || !next.trim()) return
    setError('')
    setNotice('')
    try {
      await apiRequest(`/groups/${encodeURIComponent(group.group_code)}`, { method: 'PUT', body: { description: next.trim() } })
      setNotice(`Description de ${group.group_code} mise à jour.`)
      await load()
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  async function assignDevice(deviceId, nextGroup) {
    if (!nextGroup) return
    setError('')
    setNotice('')
    try {
      await apiRequest(`/groups/${encodeURIComponent(nextGroup)}/devices/${encodeURIComponent(deviceId)}`, { method: 'PUT' })
      setNotice(`${deviceId} affecté à ${nextGroup}.`)
      await load()
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  return (
    <section className="management-page">
      <header className="management-heading">
        <div><span className="eyebrow">ADMINISTRATION</span><h1>Groupes & affectations</h1><p>Organiser les techniciens et appareils par groupe.</p></div>
        <span className="section-meta">{groups.length} groupes · {devices.length} appareils</span>
      </header>
      {error && <div className="form-error" role="alert">{error}</div>}
      {notice && <div className="form-success" role="status">{notice}</div>}
      <div className="group-admin-grid">
        <article className="panel form-panel">
          <div className="section-heading compact-heading"><div><span className="eyebrow">REGISTRE</span><h2>Créer un groupe</h2></div></div>
          <form className="form-stack" onSubmit={createGroup}>
            <label>Code du groupe<select required value={groupCode} onChange={event => setGroupCode(event.target.value)}>
              <option value="">Choisir un code disponible</option>
              {Array.from({ length: 9 }, (_, index) => `G${index + 1}`)
                .filter(code => !groups.some(group => group.group_code === code))
                .map(code => <option key={code} value={code}>{code}</option>)}
            </select></label>
            <label>Description<input required minLength={1} maxLength={255} value={description} onChange={event => setDescription(event.target.value)} /></label>
            <button className="primary-button" type="submit" disabled={saving || !groupCode}>{saving ? 'Création…' : 'Créer le groupe'}</button>
          </form>
        </article>
        {loading ? <div className="panel empty-panel">Chargement des groupes…</div> : groups.map(group => {
          const members = users.filter(user => user.group_code === group.group_code)
          const groupDevices = devices.filter(device => device.group_code === group.group_code)
          return (
            <article className="panel group-card" key={group.group_code}>
              <header className="group-card-header">
                <div><span className="group-code-badge">{group.group_code}</span><h2>{group.description || 'Groupe sans description'}</h2></div>
                <button className="subtle-button" type="button" onClick={() => updateDescription(group)}>Modifier</button>
              </header>
              <div className="group-counts"><span><strong>{members.length}</strong> utilisateurs</span><span><strong>{groupDevices.length}</strong> appareils</span></div>
              <div className="group-members">
                <h3>Utilisateurs</h3>
                {members.length ? members.map(user => <span className="member-chip" key={user.id}>{user.first_name} {user.last_name}<small>{user.role === 'admin' ? 'Admin' : 'Technicien'}</small></span>) : <p>Aucun utilisateur affecté.</p>}
              </div>
              <div className="group-members">
                <h3>Appareils</h3>
                {groupDevices.length ? groupDevices.map(device => <span className="member-chip" key={device.device_id}>{device.device_id}<small>{device.zone || 'Zone non définie'}</small></span>) : <p>Aucun appareil affecté.</p>}
              </div>
              <label className="assign-device">Affecter un appareil
                <select value="" onChange={event => assignDevice(event.target.value, group.group_code)}>
                  <option value="">Choisir un appareil…</option>
                  {devices.filter(device => device.group_code !== group.group_code)
                    .map(device => <option key={device.device_id} value={device.device_id}>{device.device_id} · {device.group_code || 'Sans groupe'} · {device.zone || 'Zone inconnue'}</option>)}
                </select>
              </label>
            </article>
          )
        })}
      </div>
    </section>
  )
}
