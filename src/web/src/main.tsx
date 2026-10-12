import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { AuthProvider } from './api/auth'
import { App } from './App'
import { ToastProvider } from './components'
import { ThemeProvider } from './theme/ThemeProvider'
import { defaultThemeFor } from './theme/tokens'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter basename="/app">
      <ThemeProvider fallback={defaultThemeFor(location.pathname.replace(/^\/app/, ''))}>
        <ToastProvider>
          <AuthProvider><App /></AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
)
