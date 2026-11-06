import { API } from './lib.js'

export async function apiRequest(path, { method = 'GET', body, signal } = {}) {
  const headers = { Accept: 'application/json' }
  const token = sessionStorage.getItem('em-token')
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const response = await fetch(API + path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
    cache: 'no-store',
  })

  if (response.status === 401 && path !== '/auth/login') {
    sessionStorage.removeItem('em-token')
    window.dispatchEvent(new Event('em-auth-expired'))
  }
  if (!response.ok) {
    let message = `Erreur API (${response.status})`
    try {
      const payload = await response.json()
      const detail = payload.detail
      message = Array.isArray(detail)
        ? detail.map(item => `${item.loc?.slice(-1)[0] || 'champ'} : ${item.msg}`).join(' · ')
        : detail || message
    } catch {}
    throw new Error(message)
  }
  if (response.status === 204) return null
  return response.json()
}
