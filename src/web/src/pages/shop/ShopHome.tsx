import { Link } from 'react-router'
import { ShopChat } from '../ai/ShopChat'
import { api, money, isStaff, hasRole } from '../../api/client'
import { useAuth } from '../../api/auth'
import { useLoad } from '../../api/useLoad'
import { Button, EmptyState } from '../../components'

// Featured shelves: subcategories that read well in a demo (CAT-03 over the SUBCAT GSI).
const shelves = [{ id: 2, title: 'Road bikes' }, { id: 31, title: 'Helmets' }]
const art: Record<string, string> = { Bikes: '🚲', Components: '⚙', Clothing: '🧥', Accessories: '⛑' }

/** Redesigned shop home (C2-2): hero, category tiles (CAT-01), featured shelves (CAT-03), offers note, staff shortcut. */
export function ShopHome() {
  const { me } = useAuth()
  const cats = useLoad(() => api.categories())
  const shelf = useLoad(() => Promise.all(shelves.map(s => api.subcategoryProducts(s.id))))
  return (
    <div className="flex flex-col gap-8">
      <ShopChat />
      <section className="relative overflow-hidden rounded-aw border border-line bg-panel px-8 py-10" aria-label="Welcome">
        <p className="text-xs tracking-widest text-accent2 uppercase">AdventureWorks Cycles</p>
        <h1 className="mt-2 max-w-2xl font-display text-4xl font-bold">Ride further. Ship faster.</h1>
        <p className="mt-3 max-w-xl text-mute">Bikes, components and gear with real prices: volume discounts and promotions applied at checkout, tax by your state or province, freight by ship method.</p>
        <div className="mt-6 flex gap-3">
          <Link to="/shop/products"><Button>Browse products</Button></Link>
          {me?.authenticated && !isStaff(me) && <Link to="/shop/cart"><Button variant="secondary">Your cart</Button></Link>}
          {hasRole(me, 'Fulfilment') && <Link to="/back-office/orders"><Button variant="secondary">Back office · orders</Button></Link>}
          {(hasRole(me, 'Buyer') || hasRole(me, 'PurchasingManager')) && <Link to="/back-office/procurement"><Button variant="secondary">Back office · procurement</Button></Link>}
          {hasRole(me, 'ProductionSupervisor') && <Link to="/back-office/production"><Button variant="secondary">Back office · production</Button></Link>}
          {!me?.authenticated && <Link to="/login"><Button variant="secondary">Sign in</Button></Link>}
        </div>
      </section>

      <section aria-labelledby="cats">
        <h2 id="cats" className="mb-3 font-display text-xl font-semibold">Shop by category</h2>
        {cats.error ? <EmptyState title="Could not load categories" /> : (
          <div className="grid grid-cols-4 gap-3.5">
            {(cats.data ?? []).map(c => (
              <div key={c.id} className="rounded-aw border border-line bg-panel p-4" data-testid="category-tile">
                <div className="text-2xl" aria-hidden>{art[c.name] ?? '◆'}</div>
                <div className="mt-1 font-semibold">{c.name}</div>
                <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm">
                  {c.subcategories.slice(0, 6).map(s => <li key={s.id}><Link className="text-mute hover:text-accent" to={`/shop/c/${s.id}`}>{s.name}</Link></li>)}
                </ul>
              </div>
            ))}
          </div>)}
      </section>

      {shelves.map((s, i) => (
        <section key={s.id} aria-labelledby={`shelf-${s.id}`}>
          <div className="mb-3 flex items-baseline gap-3">
            <h2 id={`shelf-${s.id}`} className="font-display text-xl font-semibold">{s.title}</h2>
            <Link className="text-sm text-accent" to={`/shop/c/${s.id}`}>See all</Link>
          </div>
          <div className="grid grid-cols-4 gap-3.5">
            {(shelf.data?.[i] ?? []).slice(0, 4).map(p => (
              <Link key={p.id} to={`/shop/products/${p.id}`} className="rounded-aw border border-line bg-panel p-4 hover:border-accent" data-testid="featured-product">
                <div className="text-sm text-mute">{p.productNumber}</div>
                <div className="font-semibold">{p.name}</div>
                <div className="mt-2 text-lg">{money.format(p.listPrice)}</div>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
