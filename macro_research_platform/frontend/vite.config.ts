import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,  // Frontend on port 5173
    proxy: {
      '/api': {
        target: 'http://localhost:8001',  // Backend API on port 8001
        changeOrigin: true,
      },
      '/socket.io': {
        target: 'http://localhost:8001',  // WebSocket proxy to backend
        changeOrigin: true,
        ws: true,
        secure: false,
      },
    },
  },
})
