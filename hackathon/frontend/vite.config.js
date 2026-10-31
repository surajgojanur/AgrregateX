import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: `npm run dev` proxies /api to the AgrregateX API (docker compose publishes it on 127.0.0.1:8090).
// Override with AX_API_TARGET=http://host:port npm run dev
const target = process.env.AX_API_TARGET || 'http://127.0.0.1:8090'

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5182, proxy: { '/api': { target, changeOrigin: false } } },
  preview: { host: '127.0.0.1', port: 5182, proxy: { '/api': { target, changeOrigin: false } } },
})
