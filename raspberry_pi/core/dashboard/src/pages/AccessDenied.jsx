import { Link } from 'react-router-dom'

export default function AccessDenied() {
  return (
    <main className="auth-page">
      <section className="auth-card" role="alert">
        <div className="auth-brand">
          <span className="brand-mark"><span /><span /><span /><span /></span>
          <strong>EnviroMesh</strong>
        </div>
        <span className="topbar-eyebrow">ACCÈS RESTREINT</span>
        <h1>Accès refusé</h1>
        <p>Cette ressource n’appartient pas à votre groupe ou votre compte n’a pas les droits nécessaires.</p>
        <Link className="primary-button auth-submit" to="/">Retour au tableau de bord <span aria-hidden="true">→</span></Link>
      </section>
    </main>
  )
}
