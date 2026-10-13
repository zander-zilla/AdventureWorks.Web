import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { mockApi } from './mockApi'

// C2-2 end to end: shop home, product + reviews, cart with real pricing, order placed -> approved -> shipped in the back
// office, visible in the replication monitor and in My orders; catalog admin price edit writes history.
// Mocked /api/v2 by default; against the real app image (DynamoDB Local) when AW_E2E_BASE is set (after.yml).
const real = !!process.env.AW_E2E_BASE
const shots = process.env.AW_SCREENSHOTS
const PW = 'Demo!2026'
const CUSTOMER = 'walter0@adventure-works.com'
const OPS = 'ops@adventure-works.com'

async function shot(page: Page, name: string) {
  if (!shots) return
  fs.mkdirSync(shots, { recursive: true })
  await page.screenshot({ path: path.join(shots, `c2-2-${name}${real ? '-real' : ''}.png`), fullPage: true })
}
async function setup(page: Page, t: 'dark' | 'light' = 'dark') {
  await page.addInitScript(v => localStorage.setItem('aw.theme', v), t)
  if (!real) await mockApi(page)
}
async function signIn(page: Page, email: string) {
  await page.goto('./login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(PW)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByTestId('user')).toBeVisible()
}
async function signOut(page: Page) {
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('link', { name: 'Sign in' }).first()).toBeVisible()
}

for (const t of ['dark', 'light'] as const) {
  test(`redesigned shop home (${t})`, async ({ page }) => {
    await setup(page, t)
    await page.goto('./')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Ride further. Ship faster.')
    await expect(page.getByTestId('category-tile')).toHaveCount(4)
    await expect(page.getByTestId('featured-product').first()).toBeVisible()
    await shot(page, `shop-home-${t}`)
  })
}

test('order placed -> approved -> shipped, visible in the replication monitor and My orders', async ({ page }) => {
  test.setTimeout(120_000)
  await setup(page)
  await signIn(page, CUSTOMER)

  // product page: offers, add 12 helmets (volume discount tier 11-14 when the offer applies), review
  await page.goto('./shop/products/707')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Helmet')
  await page.getByLabel('Quantity').fill('12')
  await page.getByTestId('add-to-cart').click()
  await expect(page.getByRole('status').filter({ hasText: 'Added 12' })).toBeVisible()
  await page.getByLabel('Your review').fill('Light, comfortable and the strap stays put on long rides.')
  await page.getByRole('button', { name: 'Submit review' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Thanks for your review' }).or(page.getByRole('alert'))).toBeVisible()
  await expect(page.getByTestId('review').first()).toBeVisible()
  await shot(page, 'product-reviews')

  // cart: server quote with tax + freight by ship method; switching method changes freight
  await page.goto('./shop/cart')
  await expect(page.getByTestId('cart-line')).toHaveCount(1)
  await expect(page.getByTestId('quote')).toBeVisible()
  if (!real) await expect(page.getByTestId('line-offer')).toContainText('Volume Discount 11 to 14')
  const freight1 = await page.getByTestId('freight').innerText()
  await page.getByLabel('Ship method (REF-04)').selectOption('5')
  await expect(page.getByTestId('freight')).not.toHaveText(freight1)
  await shot(page, 'checkout-quote')
  await page.getByTestId('place-order').click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/^SO-DDB-1\d{9}$/)
  const number = (await page.getByRole('heading', { level: 1 }).innerText()).trim()
  await expect(page.getByTestId('order-status')).toContainText('In process')
  await signOut(page)

  // back office: approve, then ship (one transaction: status + stock + TransactionHistory)
  await signIn(page, OPS)
  await page.goto('./back-office/orders')
  await page.getByTestId('status-tab-1').click()
  await page.getByLabel('Filter rows').fill(number)
  await shot(page, 'back-office-queue')
  await page.getByTestId('open-order').filter({ hasText: number }).click()
  await expect(page.getByRole('dialog')).toContainText('need 12')
  await page.getByTestId('action-approve').click()
  await expect(page.getByRole('status').filter({ hasText: `${number}: approve` })).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()
  await page.getByTestId('status-tab-2').click()
  await page.getByLabel('Filter rows').fill(number)
  await page.getByTestId('open-order').filter({ hasText: number }).click()
  await page.getByTestId('action-ship').click()
  await page.getByLabel('Ship method', { exact: true }).selectOption('5')
  await page.getByLabel('Tracking number').fill('1ZC22E2E0001')
  await shot(page, 'ship-drawer')
  await page.getByTestId('action-ship').click()
  await expect(page.getByRole('status').filter({ hasText: `${number} shipped` })).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()

  // replication monitor: placed, approve and ship entries for this order, ship lists the stock movement (TXN type S)
  await page.goto('./back-office/replication')
  const entries = page.getByTestId('feed-entry').filter({ hasText: number })
  await expect(entries.filter({ hasText: 'order.ship' })).toContainText('stg.inventory_transaction')
  await expect(entries.filter({ hasText: 'order.approve' })).toHaveCount(1)
  await expect(entries.filter({ hasText: 'order.placed' })).toHaveCount(1)
  await shot(page, 'replication-monitor')
  await signOut(page)

  // customer sees Shipped with tracking and the status history
  await signIn(page, CUSTOMER)
  await page.goto('./shop/orders')
  await page.getByTestId('order-link').filter({ hasText: number }).click()
  await expect(page.getByTestId('order-status')).toContainText('Shipped')
  await expect(page.getByTestId('tracking')).toHaveText('1ZC22E2E0001')
  await shot(page, 'my-order-shipped')
})

test('catalog admin edits a price: history item written (CAT-07 fix)', async ({ page }) => {
  await setup(page)
  await signIn(page, OPS)
  await page.goto('./shop/products/707')
  const history = page.getByRole('table', { name: 'Price history' })
  const before = await history.locator('tbody tr').count()
  await page.getByLabel('New list price').fill('36.49')
  await page.getByTestId('save-price').click()
  await expect(page.getByRole('status').filter({ hasText: 'history written' })).toBeVisible()
  await expect(page.getByTestId('list-price')).toHaveText('$36.49')
  await expect(history.locator('tbody tr')).toHaveCount(before + 1)
  await expect(history.locator('tbody tr').first()).toContainText('app (C2-2)')
  await shot(page, 'price-history')
})

test('back office needs a staff role; customers are told to sign in as staff', async ({ page }) => {
  await setup(page)
  await signIn(page, CUSTOMER)
  await page.goto('./back-office/orders')
  await expect(page.getByText('Back-office sign-in required')).toBeVisible()
})
