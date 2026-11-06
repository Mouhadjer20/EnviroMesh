import { useState } from 'react'
import { apiRequest } from '../api.js'

export default function Settings({ user, onUserUpdated }) {
  const [profile, setProfile] = useState({ first_name: user.first_name, last_name: user.last_name, email: user.email })
  const [passwords, setPasswords] = useState({ current_password: '', new_password: '', confirm: '' })
  const [profileError, setProfileError] = useState('')
  const [profileNotice, setProfileNotice] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [passwordNotice, setPasswordNotice] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)
  const [savingPassword, setSavingPassword] = useState(false)

  async function saveProfile(event) {
    event.preventDefault()
    setProfileError('')
    setProfileNotice('')
    setSavingProfile(true)
    try {
      const updated = await apiRequest('/auth/profile', {
        method: 'PUT',
        body: { first_name: profile.first_name.trim(), last_name: profile.last_name.trim(), email: profile.email.trim() },
      })
      onUserUpdated(updated)
      setProfileNotice('Profil mis à jour.')
    } catch (requestError) {
      setProfileError(requestError.message)
    } finally {
      setSavingProfile(false)
    }
  }

  async function changePassword(event) {
    event.preventDefault()
    setPasswordError('')
    setPasswordNotice('')
    if (passwords.new_password !== passwords.confirm) {
      setPasswordError('Les nouveaux mots de passe ne correspondent pas.')
      return
    }
    setSavingPassword(true)
    try {
      await apiRequest('/auth/change-password', {
        method: 'POST',
        body: { current_password: passwords.current_password, new_password: passwords.new_password },
      })
      const updated = await apiRequest('/auth/me')
      onUserUpdated(updated)
      setPasswords({ current_password: '', new_password: '', confirm: '' })
      setPasswordNotice('Mot de passe changé. Votre session reste ouverte.')
    } catch (requestError) {
      setPasswordError(requestError.message)
    } finally {
      setSavingPassword(false)
    }
  }

  return (
    <section className="management-page settings-page">
      <header className="management-heading">
        <div><span className="eyebrow">VOTRE COMPTE</span><h1>Paramètres du profil</h1><p>Consulter et mettre à jour vos informations personnelles et votre mot de passe.</p></div>
      </header>
      {user.password_change_required && <div className="password-required" role="alert"><strong>Changement obligatoire</strong><span>Choisissez un nouveau mot de passe pour accéder au dashboard et aux données du groupe.</span></div>}
      <div className="settings-grid">
        {!user.password_change_required && <article className="panel form-panel">
          <div className="section-heading compact-heading"><div><span className="eyebrow">PROFIL</span><h2>Informations personnelles</h2></div></div>
          {profileError && <div className="form-error" role="alert">{profileError}</div>}
          {profileNotice && <div className="form-success" role="status">{profileNotice}</div>}
          <form className="form-stack" onSubmit={saveProfile}>
            <label>Prénom<input required maxLength={100} value={profile.first_name} onChange={event => setProfile({ ...profile, first_name: event.target.value })} /></label>
            <label>Nom<input required maxLength={100} value={profile.last_name} onChange={event => setProfile({ ...profile, last_name: event.target.value })} /></label>
            <label>E-mail<input type="email" required maxLength={255} value={profile.email} onChange={event => setProfile({ ...profile, email: event.target.value })} /></label>
            <div className="profile-meta"><span>Rôle</span><strong>{user.role === 'admin' ? 'Administrateur' : 'Technicien de groupe'}</strong></div>
            <div className="profile-meta"><span>Groupe</span><strong>{user.group_code || 'Accès administrateur'}</strong></div>
            <button className="primary-button" type="submit" disabled={savingProfile}>{savingProfile ? 'Enregistrement…' : 'Enregistrer le profil'}</button>
          </form>
        </article>}
        <article className="panel form-panel">
          <div className="section-heading compact-heading"><div><span className="eyebrow">SÉCURITÉ</span><h2>Changer le mot de passe</h2></div></div>
          {passwordError && <div className="form-error" role="alert">{passwordError}</div>}
          {passwordNotice && <div className="form-success" role="status">{passwordNotice}</div>}
          <form className="form-stack" onSubmit={changePassword}>
            <label>Mot de passe actuel<input type="password" required maxLength={200} autoComplete="current-password" value={passwords.current_password} onChange={event => setPasswords({ ...passwords, current_password: event.target.value })} /></label>
            <label>Nouveau mot de passe<input type="password" required minLength={12} maxLength={200} autoComplete="new-password" value={passwords.new_password} onChange={event => setPasswords({ ...passwords, new_password: event.target.value })} /><small>12 caractères minimum.</small></label>
            <label>Confirmer le nouveau mot de passe<input type="password" required minLength={12} maxLength={200} autoComplete="new-password" value={passwords.confirm} onChange={event => setPasswords({ ...passwords, confirm: event.target.value })} /></label>
            <button className="primary-button" type="submit" disabled={savingPassword}>{savingPassword ? 'Mise à jour…' : 'Changer le mot de passe'}</button>
          </form>
        </article>
      </div>
    </section>
  )
}
