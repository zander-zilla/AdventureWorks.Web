import type { ReactNode } from 'react'
import { Route, Routes } from 'react-router'
import { useAuth } from './api/auth'
import { hasRole } from './api/client'
import { AppShell, EmptyState } from './components'
import { nav } from './nav'
import { DesignGallery } from './pages/DesignGallery'
import { Overview } from './pages/Home'
import { Login } from './pages/Login'
import { Products } from './pages/Products'
import { BackOfficeOrders } from './pages/backoffice/Orders'
import { Replication } from './pages/backoffice/Replication'
import { Cart } from './pages/shop/Cart'
import { MyOrder, MyOrders } from './pages/shop/MyOrders'
import { ProductPage } from './pages/shop/ProductPage'
import { ShopHome } from './pages/shop/ShopHome'
import { Subcategory } from './pages/shop/Subcategory'
import { chapter1Url } from './showcaseUrl'

// Chapter switch: Chapter 1 is the frozen showcase under /c1/ on the showcase site (C2-1); in the app it links out.
const goChapter1 = () => { window.location.href = chapter1Url() }

/** Back-office screens need a staff role (the API enforces it too: 401/403). */
function Staff({ role, children }: { role: string; children: ReactNode }) {
  const { me, loading } = useAuth()
  if (loading) return null
  return hasRole(me, role) ? children : <EmptyState title="Back-office sign-in required">Sign in as fulfilment@adventure-works.com or ops@adventure-works.com.</EmptyState>
}

export function App() {
  const { me, logout } = useAuth()
  return (
    <AppShell nav={nav} user={me?.authenticated ? me.name : null} chapter="c2" onChapter={c => c === 'c1' && goChapter1()} onSignOut={logout}>
      <Routes>
        <Route index element={<ShopHome />} />
        <Route path="overview" element={<Overview />} />
        <Route path="shop/products" element={<Products />} />
        <Route path="shop/products/:id" element={<ProductPage />} />
        <Route path="shop/c/:id" element={<Subcategory />} />
        <Route path="shop/cart" element={<Cart />} />
        <Route path="shop/orders" element={<MyOrders />} />
        <Route path="shop/orders/:id" element={<MyOrder />} />
        <Route path="back-office/orders" element={<Staff role="Fulfilment"><BackOfficeOrders /></Staff>} />
        <Route path="back-office/replication" element={<Staff role="Fulfilment"><Replication /></Staff>} />
        <Route path="design" element={<DesignGallery />} />
        <Route path="login" element={<Login />} />
        <Route path="*" element={<EmptyState title="Not here yet">This screen arrives in a later Chapter 2 phase.</EmptyState>} />
      </Routes>
    </AppShell>
  )
}
