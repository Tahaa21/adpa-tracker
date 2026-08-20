import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
//
// LOCAL-ONLY: no `server.host` override here on purpose — Vite's default is
// to bind the dev server to localhost only. Do not set `host: true` or
// `host: '0.0.0.0'` here; that would expose the dev server to the LAN. The
// Docker Compose frontend service needs 0.0.0.0 *inside its container* for
// Docker's port forwarding to work, but it gets that via an explicit
// `--host 0.0.0.0` CLI flag in docker-compose.yml's `command:`, not from
// this config — so the local (non-Docker) `npm run dev` path stays
// localhost-only by default.
export default defineConfig({
  plugins: [react(), tailwindcss()],
})
