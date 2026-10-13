import type { ReactNode } from 'react'
import { Route, Routes } from 'react-router'
import { useAuth } from './api/auth'
import { hasRole, staffRoles } from './api/client'
import { AppShell, EmptyState } from './components'
import { nav } from './nav'
import { DesignGallery } from './pages/DesignGallery'
import { Overview } from './pages/Home'
import { Login } from './pages/Login'
import { Products } from './pages/Products'
import { BackOfficeOrders } from './pages/backoffice/Orders'
import { Procurement } from './pages/backoffice/Procurement'
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
function Staff({ roles, children }: { roles: string[]; children: ReactNode }) {
  const { me, loading } = useAuth()
  if (loading) return null
  return roles.some(r => hasRole(me, r)) ? children : (
    <EmptyState title="Back-office sign-in required">
      {roles.includes('Buyer')
        ? 'Sign in as mikael0@adventure-works.com (Buyer) or sheela0@adventure-works.com (Purchasing manager).'
        : 'Sign in as fulfilment@adventure-works.com or ops@adventure-works.com.'}
    </EmptyState>)
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
        <Route path="back-office/orders" element={<Staff roles={['Fulfilment']}><BackOfficeOrders /></Staff>} />
        <Route path="back-office/replication" element={<Staff roles={staffRoles}><Replication /></Staff>} />
        <Route path="back-office/procurement/*" element={<Staff roles={['Buyer', 'PurchasingManager']}><Procurement /></Staff>} />
        <Route path="design" element={<DesignGallery />} />
        <Route path="login" element={<Login />} />
        <Route path="*" element={<EmptyState title="Not here yet">This screen arrives in a later Chapter 2 phase.</EmptyState>} />
      </Routes>
    </AppShell>
  )
}
