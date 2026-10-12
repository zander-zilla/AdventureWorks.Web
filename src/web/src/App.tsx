import { Route, Routes } from 'react-router'
import { useAuth } from './api/auth'
import { AppShell, EmptyState } from './components'
import { nav } from './nav'
import { DesignGallery } from './pages/DesignGallery'
import { Home } from './pages/Home'
import { Login } from './pages/Login'
import { Products } from './pages/Products'

// Chapter switch: Chapter 1 is the frozen showcase under /c1/ on the showcase site (C2-1); in the app it links out.
const goChapter1 = () => { window.location.href = (import.meta.env.VITE_SHOWCASE_URL ?? '/') + 'c1/' }

export function App() {
  const { me, logout } = useAuth()
  return (
    <AppShell nav={nav} user={me?.authenticated ? me.name : null} chapter="c2" onChapter={c => c === 'c1' && goChapter1()} onSignOut={logout}>
      <Routes>
        <Route index element={<Home />} />
        <Route path="shop/products" element={<Products />} />
        <Route path="design" element={<DesignGallery />} />
        <Route path="login" element={<Login />} />
        <Route path="*" element={<EmptyState title="Not here yet">This screen arrives in a later Chapter 2 phase.</EmptyState>} />
      </Routes>
    </AppShell>
  )
}
