import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import { resolveApiBase } from './lib/apiPort'
import './index.css'
import { applyUpDown, initTheme } from './lib/theme'
import { initBrand } from './lib/fundBrand'

initTheme()   // before first paint: no dark→light flash
initBrand()   // the selected fund's remembered brand, also before first paint
applyUpDown()

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
