import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

/** Read the port the Python backend wrote on startup. */
function getApiPort(): number {
  // Check project root for .api_port file
  const portFile = path.resolve(__dirname, "..", ".api_port")
  try {
    const content = fs.readFileSync(portFile, 'utf-8').trim()
    const port = parseInt(content, 10)
    if (!isNaN(port)) return port
  } catch {
    // .api_port not yet written — use env or default
  }
  return parseInt(process.env.API_PORT ?? "8000", 10)
}

export default defineConfig(({ mode }) => {
  // FIXED (Fix 1): Load env variables properly
  const env = loadEnv(mode, process.cwd(), '')
  const apiPort = parseInt(env.VITE_API_PORT || String(getApiPort()), 10)
  const apiHost = env.VITE_API_HOST || 'localhost'

  console.log(`[vite] Proxying /api → http://${apiHost}:${apiPort}`)

  return {
    plugins: [react()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "./src") },
    },
    build: {
      emptyOutDir: false,  // Don't delete old dist files — avoids EPERM on macOS-mounted folders
    },
    server: {
      port: parseInt(process.env.VITE_PORT ?? "5173", 10),
      proxy: {
        "/api": {
          target: `http://${apiHost}:${apiPort}`,
          changeOrigin: true,
          secure: false,
          ws: true,   // FIXED (Fix 1): Proxy WebSocket upgrades
        },
        "/socket.io": {
          target: `http://${apiHost}:${apiPort}`,
          changeOrigin: true,
          ws: true,   // FIXED (Fix 1): Proxy Socket.IO handshake
          secure: false,
        },
      },
    },
  }
})
