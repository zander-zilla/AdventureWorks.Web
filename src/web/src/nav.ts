import type { NavGroup } from './components'

// Later phases are listed but disabled so the shell shows the whole Chapter 2 map from day one.
export const nav: NavGroup[] = [
  { title: 'Overview', items: [{ to: '/', label: 'Home', icon: '◧' }] },
  { title: 'Shop', items: [{ to: '/shop/products', label: 'Products', icon: '▦' }] },
  { title: 'Back office', items: [
    { to: '/back-office/orders', label: 'Orders', icon: '⇄', badge: 'C2-2', disabled: true },
    { to: '/procurement', label: 'Procurement', icon: '⛟', badge: 'C2-3', disabled: true },
    { to: '/production', label: 'Production', icon: '⚙', badge: 'C2-4', disabled: true },
  ] },
  { title: 'Design', items: [{ to: '/design', label: 'Component gallery', icon: '◈' }] },
]
