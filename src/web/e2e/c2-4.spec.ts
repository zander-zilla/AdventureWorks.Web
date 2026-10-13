import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { mockApi } from './mockApi'

// C2-4 end to end: scrap & on-time KPIs (INV-06, Recharts) -> supervisor plans and creates a work order (standard routing,
// level-1 components from INV-04) -> records an operation (Gantt) -> completes with scrap (stock in, components out,
// TransactionHistory W) -> replication monitor -> BOM explorer with where-used (INV-05) -> a SQL-era work order is read-only.
// Mocked /api/v2 by default; against the real app image + DynamoDB Local when AW_E2E_BASE is set.
const real = !!process.env.AW_E2E_BASE
const shots = process.env.AW_SCREENSHOTS
const PW = 'Demo!2026'
const SUPERVISOR = 'production@adventure-works.com'

async function shot(page: Page, name: string) {
  if (!shots) return
  fs.mkdirSync(shots, { recursive: true })
  await page.screenshot({ path: path.join(shots, `c2-4-${name}${real ? '-real' : ''}.png`), fullPage: true })
}
async function setup(page: Page) {
  await page.addInitScript(() => localStorage.setItem('aw.theme', 'dark'))
  if (!real) await mockApi(page)
}
async function signIn(page: Page, email: string) {
  await page.goto('./login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(PW)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByTestId('user')).toBeVisible()
}

test('scrap & on-time -> create work order -> record operation -> complete with scrap -> replication -> BOM + where-used', async ({ page }) => {
  test.setTimeout(240_000)
  await setup(page)
  await signIn(page, SUPERVISOR)
  await page.goto('./back-office/production')
  await expect(page.getByTestId('kpi-scrap')).toContainText('%', { timeout: 90_000 })
  await expect(page.getByTestId('kpi-ontime')).toContainText('%')
  await expect(page.getByTestId('scrap-chart').locator('.recharts-bar-rectangle').first()).toBeVisible()
  await shot(page, 'scrap-on-time')

  // plan: first top-level assembly whose level-1 components are all in stock
  await page.goto('./back-office/production/work-orders')
  await page.getByTestId('new-wo').click()
  const select = page.getByTestId('wo-product')
  await expect(select.locator('option')).not.toHaveCount(1, { timeout: 30_000 })
  await page.getByTestId('wo-qty').fill('2')
  const values = await select.locator('option').evaluateAll(os => os.map(o => (o as HTMLOptionElement).value).filter(Boolean))
  const preferred = values.slice(0, 60)
  let picked = false
  for (const v of preferred) {
    await select.selectOption(v)
    const ok = page.getByTestId('wo-plan-ok'), blocked = page.getByTestId('wo-plan-blocked')
    await expect(ok.or(blocked)).toBeVisible({ timeout: 30_000 })
    if (await ok.isVisible() && await page.getByRole('table', { name: 'Components' }).getByRole('row').count() > 1) { picked = true; break }
  }
  expect(picked).toBe(true)
  await expect(page.getByTestId('gantt-step').first()).toBeVisible()
  await shot(page, 'new-work-order')
  await page.getByTestId('wo-create').click()
  const created = page.getByRole('status').filter({ hasText: /WO-DDB-\d+ created/ })
  await expect(created).toBeVisible()
  const number = (await created.innerText()).match(/WO-DDB-\d+/)![0]
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText(number)
  await expect(page.getByTestId('wo-state')).toContainText('Open')

  // record the first operation, then complete with 1 of 2 scrapped
  await page.getByTestId('op-hrs').fill('3.5')
  await page.getByTestId('record-op').click()
  await expect(page.getByRole('status').filter({ hasText: `${number}: operation recorded` })).toBeVisible()
  await expect(dialog.getByRole('table', { name: 'Routing steps' })).toContainText('3.5')
  await shot(page, 'routing-gantt')
  await page.getByTestId('complete-wo').click()
  await page.getByTestId('scrap-qty').fill('1')
  await page.getByTestId('scrap-reason').selectOption({ index: 1 })
  await shot(page, 'complete')
  await page.getByTestId('complete-wo').click()
  await expect(page.getByRole('status').filter({ hasText: `${number} completed` })).toBeVisible()
  await expect(page.getByTestId('wo-state')).toContainText('Closed')
  await expect(dialog).toContainText('Stocked · scrapped')
  await expect(page.getByTestId('complete-wo')).toHaveCount(0)
  await shot(page, 'work-order-complete')
  await page.getByRole('button', { name: 'Close' }).click()

  // replication monitor: create, operation and completion with the stock movements (TransactionHistory W)
  await page.goto('./back-office/replication')
  const entries = page.getByTestId('feed-entry').filter({ hasText: number })
  await expect(entries.filter({ hasText: 'wo.complete' })).toContainText('type W')
  await expect(entries.filter({ hasText: 'wo.complete' })).toContainText('component consumed')
  await expect(entries.filter({ hasText: 'wo.create' })).toHaveCount(1)
  await shot(page, 'replication')

  // BOM explorer: multi-level tree, then where-used for a component
  await page.goto('./back-office/production/bom')
  await expect(page.getByTestId('bom-node').nth(2)).toBeVisible({ timeout: 60_000 })
  await page.getByTestId('bom-node').nth(1).getByRole('button').last().click()
  await expect(page.getByTestId('used-node').nth(1)).toBeVisible({ timeout: 30_000 })
  await shot(page, 'bom-explorer')
})

test('SQL-era work orders are read-only, with their routing', async ({ page }) => {
  test.setTimeout(120_000)
  await setup(page)
  await signIn(page, SUPERVISOR)
  await page.goto('./back-office/production/work-orders')
  await page.getByTestId('wo-month').selectOption('2014-05')
  const row = page.getByRole('row').filter({ hasText: 'SQL-era, read-only' }).first()
  await expect(row).toBeVisible({ timeout: 60_000 })
  await row.getByTestId('open-wo').click()
  await expect(page.getByRole('dialog')).toContainText('SQL-era · read-only')
  await expect(page.getByTestId('record-op')).toHaveCount(0)
  await expect(page.getByTestId('complete-wo')).toHaveCount(0)
  await shot(page, 'historical-wo')
})

test('only a production supervisor creates work orders; other staff can look', async ({ page }) => {
  await setup(page)
  await signIn(page, 'mikael0@adventure-works.com')
  await page.goto('./back-office/production/work-orders')
  await expect(page.getByText('Sign in as production@adventure-works.com to create')).toBeVisible()
  await expect(page.getByTestId('new-wo')).toHaveCount(0)
})
