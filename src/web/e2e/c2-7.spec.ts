import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

// C2-7 synthetic data: only against the real image over DynamoDB Local loaded with the generated slice
// (scripts/synthetic-up.sh, then after-up with SKIP_LOAD=1), i.e. AW_E2E_BASE + AW_SYNTHETIC_END set (CI job synthetic-e2e).
const end = process.env.AW_SYNTHETIC_END
const year = end ? end.slice(0, 4) : ''
const shots = process.env.AW_SCREENSHOTS
test.skip(!process.env.AW_E2E_BASE || !end, 'needs the real app over the generated slice (AW_E2E_BASE + AW_SYNTHETIC_END)')

async function shot(page: Page, name: string) {
  if (!shots) return
  fs.mkdirSync(shots, { recursive: true })
  await page.screenshot({ path: path.join(shots, `c2-7-${name}.png`), fullPage: true })
}
async function signIn(page: Page, email: string) {
  await page.addInitScript(() => localStorage.setItem('aw.theme', 'dark'))
  await page.goto('./login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('Demo!2026')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByTestId('user')).toBeVisible()
}

test('a generated bike line: cloned model in a new colour, on sale from its release date', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('aw.theme', 'dark'))
  await page.goto('./shop/products/5010')  // first release (2014-09-01): ids 5010.. (10 slots per release)
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Touring-3000 Ice (2014)')
  await shot(page, 'new-product')
})

test('generated reviews on a product page', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('aw.theme', 'dark'))
  await page.goto('./shop/products/711')
  await expect(page.getByTestId('review').first()).toBeVisible({ timeout: 30_000 })
  await shot(page, 'reviews')
})

test(`checkout prices with the ${year} offers (no 2014-05-01 offer date)`, async ({ page }) => {
  await signIn(page, 'walter0@adventure-works.com')
  await page.goto('./shop/products/707')
  await page.getByLabel('Quantity').fill('11')
  await page.getByTestId('add-to-cart').click()
  await expect(page.getByRole('status').filter({ hasText: 'Added 11' })).toBeVisible()  // the cart write lands before we leave
  await page.goto('./shop/cart')
  await expect(page.getByTestId('quote')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId('line-offer').first()).toContainText(`Volume Discount 11 to 14 (${year})`)
  await shot(page, 'offers-checkout')
})

test('generated orders in the fulfilment queue', async ({ page }) => {
  await signIn(page, 'ops@adventure-works.com')
  await page.goto('./back-office/orders')
  await page.getByTestId('status-tab-1').click()
  await expect(page.getByTestId('open-order').filter({ hasText: /SO1\d{6}/ }).first()).toBeVisible({ timeout: 60_000 })
  await shot(page, 'orders-queue')
})

test('production KPIs and the smart reorder forecast over the generated years', async ({ page }) => {
  test.setTimeout(150_000)
  await signIn(page, 'ops@adventure-works.com')
  await page.goto('./back-office/production')
  await expect(page.getByTestId('kpi-scrap')).toContainText('%', { timeout: 90_000 })
  await expect(page.getByTestId('scrap-chart').locator('.recharts-bar-rectangle').first()).toBeVisible()
  await shot(page, 'production')
  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, 'mikael0@adventure-works.com')
  await page.goto('./back-office/procurement')
  await expect(page.getByTestId('smart-bar')).toBeVisible({ timeout: 60_000 })
  await page.getByTestId('vendor-group').first().getByTestId('suggestion').first().getByTestId('smart-qty').click()
  await expect(page.getByTestId('forecast-chart')).toBeVisible()
  await shot(page, 'smart-reorder')
})
