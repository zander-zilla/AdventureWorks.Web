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

test('smart reorder: forecast quantities with a chart and explanation, PO e-mail draft (draft only)', async ({ page }) => {
  test.setTimeout(150_000)
  await setup(page)
  await signIn(page, 'mikael0@adventure-works.com')
  await page.goto('./back-office/procurement')
  await expect(page.getByTestId('smart-bar')).toBeVisible({ timeout: 60_000 })
  const group = page.getByTestId('vendor-group').last()
  const row = group.getByTestId('suggestion').last()
  await row.getByTestId('smart-qty').click()
  await expect(page.getByTestId('forecast-chart')).toBeVisible()
  await page.getByTestId('explain-reorder').click()
  await expect(page.getByTestId('smart-why').getByTestId('assist-text')).toContainText('Suggest', { timeout: 30_000 })
  await shot(page, 'smart-reorder')

  // use the forecast quantities, keep one line (the last group, so the C2-3 spec's first group is untouched) and create the PO
  await page.getByTestId('use-forecast').click()
  const smartQty = Number(await row.getByTestId('smart-qty').innerText())
  if (smartQty > 0) await expect(row.getByRole('spinbutton')).toHaveValue(String(smartQty))
  const boxes = group.getByRole('checkbox')
  const n = await boxes.count()
  for (let i = 0; i < n - 1; i++) await boxes.nth(i).uncheck()
  await row.getByRole('spinbutton').fill('3')
  await group.getByTestId('create-po').click()
  await expect(page.getByRole('status').filter({ hasText: /PO-DDB-\d+ created/ })).toBeVisible()
  await page.getByTestId('po-email-draft').click()
  await expect(page.getByTestId('po-email-text')).toHaveValue(/Subject: Purchase order PO-DDB-\d+[\s\S]*Dear /, { timeout: 30_000 })
  await expect(page.getByTestId('po-email-text')).not.toHaveValue(/\[[a-z0-9_.]+\]/)
  await expect(page.getByTestId('po-email-mailto')).toHaveAttribute('href', /^mailto:\?subject=Purchase%20order/)
  await shot(page, 'po-email')
})

test('replication watchdog: rules name the cause per scenario, the model explains with the runbook', async ({ page }) => {
  await setup(page)
  await signIn(page, 'ops@adventure-works.com')
  await page.goto('./back-office/replication')
  await expect(page.getByTestId('watchdog-cause')).toContainText('healthy', { timeout: 30_000 })
  await page.getByTestId('scenario-dlq').click()
  await expect(page.getByTestId('watchdog-cause')).toContainText('dead-letter queue')
  await expect(page.getByTestId('dlq-samples')).toContainText('not found')
  await page.getByTestId('watchdog-explain').click()
  await expect(page.getByTestId('watchdog').getByTestId('assist-text')).toContainText('redrive', { timeout: 30_000 })
  await shot(page, 'watchdog-dlq')
  await page.getByTestId('scenario-lag-spike').click()
  await expect(page.getByTestId('watchdog-cause')).toContainText('backlog')
  await page.getByTestId('watchdog-explain').click()
  await expect(page.getByTestId('watchdog').getByTestId('assist-text')).toContainText('186000 ms')
  await shot(page, 'watchdog-lag')
})
