import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// En développement, /api est transmis à nginx (docker compose) : adapte le port avec VITE_API_PROXY
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    server: { proxy: { '/api': { target: env.VITE_API_PROXY || 'http://localhost:8081', changeOrigin: true } } },
  }
})
