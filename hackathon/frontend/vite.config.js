import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The old Revelio/WitnessTrace proxies (/api, /wt-api → 127.0.0.1:8021) were removed with that backend.
// Until the AggregateX backend exists the app runs in preview mode (src/services/previewBackend.js) and
// makes no API requests. Add the new backend's proxy here when it is implemented.
export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5182 },
  preview: { host: '127.0.0.1', port: 5182 },
})
