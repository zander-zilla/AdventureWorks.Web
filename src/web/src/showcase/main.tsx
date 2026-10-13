import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router'
import { ThemeProvider } from '../theme/ThemeProvider'
import '../index.css'
import { Showcase } from './Showcase'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter><ThemeProvider fallback="dark"><Showcase /></ThemeProvider></HashRouter>
  </StrictMode>,
)
