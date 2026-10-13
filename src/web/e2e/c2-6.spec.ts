import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { mockApi } from './mockApi'

// C2-6 AI everywhere (enable_ai; mocked model): triage copilot, smart reorder, replication watchdog, shopper chat.
// Mocked /api/v2 by default; against the real image (Ai__Mode=mock) when AW_E2E_BASE is set.
const real = !!process.env.AW_E2E_BASE
const shots = process.env.AW_SCREENSHOTS

async function shot(page: Page, name: string) {
  if (!shots) return
  fs.mkdirSync(shots, { recursive: true })
  await page.screenshot({ path: path.join(shots, `c2-6-${name}${real ? '-real' : ''}.png`), fullPage: true })
}
async function setup(page: Page) {
  await page.addInitScript(() => localStorage.setItem('aw.theme', 'dark'))
  if (!real) await mockApi(page)
}
async function signIn(page: Page, email: string) {
  await page.goto('./login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('Demo!2026')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByTestId('user')).toBeVisible()
}

test('triage copilot: explain with cited facts, draft the approve note into the order note', async ({ page }) => {
  test.setTimeout(120_000)
  await setup(page)
  // place an order so the queue has one (mock queue starts empty; real queue gets a fresh In process order)
  await signIn(page, 'walter0@adventure-works.com')
  await page.goto('./shop/products/707')
  await page.getByLabel('Quantity').fill('2')
  await page.getByTestId('add-to-cart').click()
  await page.goto('./shop/cart')
  await page.getByTestId('place-order').click()
  await expect(page.getByTestId('order-status')).toContainText('In process')
  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, 'ops@adventure-works.com')
  await page.goto('./back-office/orders')
  await page.getByTestId('open-order').first().click({ timeout: 60_000 })
  await page.getByTestId('triage-explain').click()
  await expect(page.getByTestId('assist-text')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('assist-cite').first()).toBeVisible()
  await shot(page, 'triage-explain')
  await page.getByTestId('triage-approve-note').click()
  await expect(page.getByTestId('order-note')).toHaveValue(/Approved SO/)
  await expect(page.getByTestId('order-note')).not.toHaveValue(/\[/)
  await shot(page, 'triage-note')
})
