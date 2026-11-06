import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiRequest } from '../api.js'

export default function Login({ onSuccess }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const navigate = useNavigate()

  async function submit(event) {
    event.preventDefault()
    setError('')
    setPending(true)
    try {
      const result = await apiRequest('/auth/login', { method: 'POST', body: { email, password } })
      sessionStorage.setItem('em-token', result.access_token)
      onSuccess(result.user)
      navigate(result.user.password_change_required ? '/settings' : '/', { replace: true })
    } catch (requestError) {
      setError(requestError.message || 'Connexion impossible.')
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand"><span className="brand-mark"><span /><span /><span /><span /></span><strong>EnviroMesh</strong></div>
        <span className="eyebrow"><i /> ESPACE DE SURVEILLANCE</span>
        <h1>Bon retour.</h1>
        <p>Connectez-vous pour accéder aux données de votre groupe.</p>
        {error && <div className="form-error" role="alert">{error}</div>}
        <form className="form-stack" onSubmit={submit}>
          <label>E-mail
            <input type="email" autoComplete="username" required maxLength={255} value={email} onChange={event => setEmail(event.target.value)} />
          </label>
          <label>Mot de passe
            <input type="password" autoComplete="current-password" required maxLength={200} value={password} onChange={event => setPassword(event.target.value)} />
          </label>
          <button className="primary-button auth-submit" type="submit" disabled={pending}>{pending ? 'Connexion…' : 'Se connecter'} <span aria-hidden="true">→</span></button>
        </form>
        <div className="auth-foot"><i /> Accès protégé · Les droits sont contrôlés par le serveur</div>
      </section>
    </main>
  )
}
