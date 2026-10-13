import type { NavGroup } from './components'

// Later phases are listed but disabled so the shell shows the whole Chapter 2 map from day one.
export const nav: NavGroup[] = [
  { title: 'Shop', items: [
    { to: '/', label: 'Home', icon: '◧' },
    { to: '/shop/products', label: 'Products', icon: '▦' },
    { to: '/shop/cart', label: 'Cart & checkout', icon: '◫' },
    { to: '/shop/orders', label: 'My orders', icon: '☰' },
  ] },
  { title: 'Back office', items: [
    { to: '/back-office/orders', label: 'Orders', icon: '⇄' },
    { to: '/back-office/replication', label: 'Replication monitor', icon: '⟳' },
    { to: '/back-office/procurement', label: 'Procurement', icon: '⛟' },
    { to: '/back-office/production', label: 'Production', icon: '⚙' },
  ] },
  { title: 'Chapter 2', items: [
    { to: '/overview', label: 'Overview', icon: '◎' },
    { to: '/design', label: 'Component gallery', icon: '◈' },
  ] },
]
