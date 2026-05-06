import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import { resolveApiBase } from './lib/apiPort'
import './index.css'

async function bootstrap() {
  // Resolve API port BEFORE mounting React
  await resolveApiBase();

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <AuthProvider>
        <App />
      </AuthProvider>
    </React.StrictMode>,
  )
}

bootstrap()
