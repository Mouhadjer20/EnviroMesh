import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../api.js'
import { useData } from '../context/DataContext.jsx'

const blank = { first_name: '', last_name: '', email: '', role: 'zone_technician', group_code: '', password: '' }

export default function UserManagement({ currentUser }) {
  const { groups } = useData()
  const [users, setUsers] = useState([])
  const [form, setForm] = useState(blank)
  const [editing, setEditing] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const loadUsers = useCallback(async () => {
    setLoading(true)
    try {
      setUsers(await apiRequest('/users/'))
      setError('')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { loadUsers() }, [loadUsers])

  function editUser(user) {
    setEditing(user.id)
    setNotice('')
    setForm({ first_name: user.first_name, last_name: user.last_name, email: user.email,
      role: user.role, group_code: user.group_code || '', password: '' })
  }

  function resetForm() {
    setEditing('')
    setForm(blank)
    setError('')
    setNotice('')
  }

  async function saveUser(event) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setNotice('')
    const body = {
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      email: form.email.trim(),
      role: form.role,
      group_code: form.group_code || null,
    }
    if (form.password) body.password = form.password
    try {
      if (editing) await apiRequest(`/users/${encodeURIComponent(editing)}`, { method: 'PUT', body })
      else await apiRequest('/users/', { method: 'POST', body })
      resetForm()
      setNotice(editing ? 'Compte mis à jour.' : 'Compte créé. Le nouvel utilisateur devra changer son mot de passe.')
      await loadUsers()
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSaving(false)
    }
  }

  async function toggleActive(user) {
    const action = user.active ? 'Désactiver' : 'Réactiver'
    if (!window.confirm(`${action} le compte de ${user.first_name} ${user.last_name} ?`)) return
    setError('')
    setNotice('')
    try {
      await apiRequest(`/users/${encodeURIComponent(user.id)}`, { method: 'PUT', body: { active: !user.active } })
      setNotice(`Compte ${user.active ? 'désactivé' : 'réactivé'}.`)
      await loadUsers()
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  return (
    <section className="management-page">
      <header className="management-heading">
        <div><span className="eyebrow">ADMINISTRATION</span><h1>Utilisateurs & rôles</h1><p>Créer des comptes et limiter chaque technicien à son groupe.</p></div>
        <span className="section-meta">{users.length} comptes</span>
      </header>
      <div className="management-grid">
        <article className="panel management-panel">
          <div className="section-heading compact-heading"><div><span className="eyebrow">COMPTES</span><h2>Utilisateurs enregistrés</h2></div></div>
          {error && <div className="form-error" role="alert">{error}</div>}
          {notice && <div className="form-success" role="status">{notice}</div>}
          {loading ? <div className="empty-panel">Chargement…</div> : (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead><tr><th>Utilisateur</th><th>Rôle</th><th>Groupe</th><th>Statut</th><th>Actions</th></tr></thead>
                <tbody>{users.map(user => (
                  <tr key={user.id}>
                    <td><strong>{user.first_name} {user.last_name}</strong><small>{user.email}</small></td>
                    <td><span className={`role-pill ${user.role === 'admin' ? 'admin' : ''}`}>{user.role === 'admin' ? 'Admin' : 'Technicien'}</span></td>
                    <td>{user.group_code || 'Tous les groupes'}</td>
                    <td><span className={`status-pill ${user.active ? 'online' : ''}`}>{user.active ? 'Actif' : 'Désactivé'}</span>{user.password_change_required && <small className="table-hint">Changement de mot de passe requis</small>}</td>
                    <td><div className="table-actions"><button type="button" className="subtle-button" onClick={() => editUser(user)}>Modifier</button>
                      <button type="button" className="subtle-button" disabled={user.id === currentUser.id} onClick={() => toggleActive(user)}>{user.active ? 'Désactiver' : 'Réactiver'}</button></div></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </article>

        <article className="panel form-panel">
          <div className="section-heading compact-heading"><div><span className="eyebrow">{editing ? 'MODIFICATION' : 'NOUVEAU COMPTE'}</span><h2>{editing ? 'Modifier le compte' : 'Créer un utilisateur'}</h2></div></div>
          <form className="form-stack" onSubmit={saveUser}>
            <div className="form-two-col">
              <label>Prénom<input required maxLength={100} value={form.first_name} onChange={event => setForm({ ...form, first_name: event.target.value })} /></label>
              <label>Nom<input required maxLength={100} value={form.last_name} onChange={event => setForm({ ...form, last_name: event.target.value })} /></label>
            </div>
            <label>E-mail<input type="email" required maxLength={255} value={form.email} onChange={event => setForm({ ...form, email: event.target.value })} /></label>
            <label>Rôle<select value={form.role} onChange={event => setForm({ ...form, role: event.target.value })}>
              <option value="zone_technician">Technicien de groupe</option><option value="admin">Administrateur</option>
            </select></label>
            {form.role === 'zone_technician' && <label>Groupe obligatoire<select required value={form.group_code} onChange={event => setForm({ ...form, group_code: event.target.value })}>
              <option value="">Choisir un groupe</option>{groups.map(group => <option key={group.group_code} value={group.group_code}>{group.group_code} · {group.description || 'Groupe'}</option>)}
            </select></label>}
            <label>{editing ? 'Nouveau mot de passe (facultatif)' : 'Mot de passe temporaire'}
              <input type="password" required={!editing} minLength={12} maxLength={200} autoComplete="new-password" value={form.password} onChange={event => setForm({ ...form, password: event.target.value })} />
              <small>{editing ? 'Si vous le définissez, l’utilisateur devra le changer à la prochaine connexion.' : '12 caractères minimum ; changement obligatoire à la première connexion.'}</small>
            </label>
            <div className="form-actions"><button className="primary-button" type="submit" disabled={saving}>{saving ? 'Enregistrement…' : editing ? 'Enregistrer les modifications' : 'Créer le compte'}</button>
              {editing && <button className="subtle-button" type="button" onClick={resetForm}>Annuler</button>}</div>
          </form>
        </article>
      </div>
    </section>
  )
}
