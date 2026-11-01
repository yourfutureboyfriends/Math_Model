// App entry: applies the theme and fund brand before first paint, then mounts <App/>.
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import { AuthProvider } from './context/AuthContext'
import { resolveApiBase } from './lib/apiPort'
import './index.css'
import { applyUpDown, initTheme } from './lib/theme'
import { initBrand } from './lib/fundBrand'
import { installTruncationTitles } from './lib/truncationTitles'
import { installAccentContrast } from './lib/accentContrast'

initTheme()   // before first paint: no dark→light flash
initBrand()   // the selected fund's remembered brand, also before first paint
applyUpDown()
installTruncationTitles()   // cut-off text shows in full on hover, everywhere
installAccentContrast()     // text on the accent colour stays readable for every theme and fund brand

async function bootstrap() {
  // Resolve API port BEFORE mounting React
  await resolveApiBase();

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <AuthProvider>
        <ErrorBoundary sectionName="Terminal"><App /></ErrorBoundary>
      </AuthProvider>
    </React.StrictMode>,
  )
}

bootstrap()
