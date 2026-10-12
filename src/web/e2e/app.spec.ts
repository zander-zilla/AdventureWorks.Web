import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

// Runs against `vite preview` with /api/v2 mocked (or against the real app when AW_E2E_BASE is set; mocks then skipped).
const real = !!process.env.AW_E2E_BASE
const shots = process.env.AW_SCREENSHOTS
const products = { items: [{ id: 680, name: 'HL Road Frame - Black, 58', productNumber: 'FR-R92B-58', listPrice: 1431.5, active: true },
  { id: 771, name: 'Mountain-100 Silver, 38', productNumber: 'BK-M82S-38', listPrice: 3399.99, active: false }], next: null }

async function mock(page: Page) {
  if (real) return
  let authed = false
  await page.route('**/api/v2/me', r => r.fulfill({ json: authed ? { authenticated: true, name: 'Donald Garcia', roles: ['Customer'] } : { authenticated: false, roles: [] } }))
  await page.route('**/api/v2/products*', r => r.fulfill({ json: products }))
  await page.route('**/api/v2/auth/login', async r => {
    const b = r.request().postDataJSON()
    if (r.request().headers()['x-aw-client'] !== 'spa') return r.fulfill({ status: 400 })
    if (b.password !== 'Demo!2026') return r.fulfill({ status: 401, json: { title: 'Unauthorized', status: 401 } })
    authed = true; return r.fulfill({ json: { authenticated: true, name: 'Donald Garcia', roles: ['Customer'] } })
  })
}
async function shot(page: Page, name: string) {
  if (!shots) return
  fs.mkdirSync(shots, { recursive: true })
  await page.screenshot({ path: path.join(shots, name), fullPage: true })
}
async function theme(page: Page, t: 'dark' | 'light') { await page.addInitScript(v => localStorage.setItem('aw.theme', v), t) }

for (const t of ['dark', 'light'] as const) {
  test(`app shell + home (${t})`, async ({ page }) => {
    await mock(page); await theme(page, t)
    await page.goto('./')
    await expect(page.locator('html')).toHaveAttribute('data-theme', t)
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Chapter 2')
    await expect(page.getByRole('navigation', { name: 'Main' })).toContainText('Component gallery')
    await expect(page.getByTestId('kpi')).toHaveCount(4)
    await shot(page, `app-shell-${t}.png`)
  })
  test(`component gallery (${t})`, async ({ page }) => {
    await mock(page); await theme(page, t)
    await page.goto('./design')
    await expect(page.getByRole('heading', { name: 'Component gallery' })).toBeVisible()
    for (const s of ['Tokens', 'KpiCard', 'Timeline', 'Chart wrapper', 'EmptyState']) await expect(page.getByRole('heading', { name: s })).toBeVisible()
    await shot(page, `component-gallery-${t}.png`)
  })
  test(`products over /api/v2 (${t})`, async ({ page }) => {
    await mock(page); await theme(page, t)
    await page.goto('./shop/products')
    await expect(page.getByRole('table', { name: 'Products' })).toContainText(real ? '$' : 'FR-R92B-58')
    await shot(page, `products-${t}.png`)
  })
}

test('theme toggle persists across reload', async ({ page }) => {
  await mock(page); await page.goto('./')
  const before = await page.locator('html').getAttribute('data-theme')
  await page.getByTestId('theme-toggle').click()
  await page.reload()
  await expect(page.locator('html')).not.toHaveAttribute('data-theme', before!)
})

test('gallery: select rows, ship drawer, toast', async ({ page }) => {
  await mock(page); await page.goto('./design')
  await page.getByLabel('Select SO75122').check(); await page.getByLabel('Select SO75121').check()
  await expect(page.getByTestId('selected-count')).toHaveText('2 selected')
  await page.getByRole('button', { name: 'Ship…' }).click()
  await expect(page.getByRole('dialog', { name: 'Ship orders' })).toBeVisible()
  await shot(page, 'drawer-dark.png')
  await page.getByRole('dialog').getByRole('button', { name: 'Ship', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Shipped (demo)' })).toBeVisible()
})

test('sign in through /api/v2 (same-origin cookie)', async ({ page }) => {
  await mock(page); await page.goto('./login')
  await page.getByLabel('Email').fill('donald0@adventure-works.com')
  await page.getByLabel('Password').fill('wrong'); await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByText('Unknown email or wrong password')).toBeVisible()
  await page.getByLabel('Password').fill('Demo!2026'); await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByTestId('user')).toContainText('Donald')
})
