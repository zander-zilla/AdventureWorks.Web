import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { mockApi } from './mockApi'

// C2-3 end to end: reorder suggestions (INV-02 + PUR-02) -> buyer creates a PO -> purchasing manager approves -> partial
// receipt with a reject, then the rest -> Complete; the replication monitor lists the PO writes incl. TransactionHistory P;
// vendor page shows performance. Mocked /api/v2 by default; against the real app image + DynamoDB Local when AW_E2E_BASE is set.
const real = !!process.env.AW_E2E_BASE
const shots = process.env.AW_SCREENSHOTS
const PW = 'Demo!2026'
const BUYER = 'mikael0@adventure-works.com'
const MANAGER = 'sheela0@adventure-works.com'

async function shot(page: Page, name: string) {
  if (!shots) return
  fs.mkdirSync(shots, { recursive: true })
  await page.screenshot({ path: path.join(shots, `c2-3-${name}${real ? '-real' : ''}.png`), fullPage: true })
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
async function signOut(page: Page) {
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('link', { name: 'Sign in' }).first()).toBeVisible()
}
async function openPo(page: Page, tab: '1' | '2' | 'mine', number: string) {
  await page.goto('./back-office/procurement/orders')
  await page.getByTestId(`po-tab-${tab}`).click()
  await page.getByLabel('Filter rows').fill(number)
  await page.getByTestId('open-po').filter({ hasText: number }).click()
  await expect(page.getByRole('dialog')).toContainText(number)
}

test('low stock -> suggested PO -> approve -> partial + final receipt -> replication + vendor performance', async ({ page }) => {
  test.setTimeout(180_000)
  await setup(page)
  await signIn(page, BUYER)
  await page.goto('./back-office/procurement')
  const group = page.getByTestId('vendor-group').first()
  await expect(group).toBeVisible({ timeout: 60_000 })
  await shot(page, 'suggestions')

  // buyer keeps only the first line of the first vendor's suggestion and creates the PO
  const vendorName = (await group.locator('header b').innerText()).trim()
  const boxes = group.getByRole('checkbox')
  for (let i = 1; i < await boxes.count(); i++) await boxes.nth(i).uncheck()
  const qty = group.getByRole('spinbutton').first()
  const suggested = Number(await qty.inputValue())
  const ordered = Math.max(2, Math.min(suggested, 40))
  await qty.fill(String(ordered))
  await group.getByTestId('create-po').click()
  await expect(page.getByRole('status').filter({ hasText: /PO-DDB-\d+ created/ })).toBeVisible()
  const number = (await page.getByRole('status').filter({ hasText: /PO-DDB-\d+ created/ }).innerText()).match(/PO-DDB-\d+/)![0]
  await expect(page.getByRole('dialog')).toContainText('Waiting for a purchasing manager')
  await expect(page.getByTestId('po-approve')).toHaveCount(0)            // buyers cannot approve
  await shot(page, 'po-created')
  await page.getByRole('button', { name: 'Close' }).click()
  await signOut(page)

  // purchasing manager approves
  await signIn(page, MANAGER)
  await openPo(page, '1', number)
  await expect(page.getByTestId('po-status')).toContainText('Pending')
  await shot(page, 'approve')
  await page.getByTestId('po-approve').click()
  await expect(page.getByRole('status').filter({ hasText: `${number} approved` })).toBeVisible()
  await expect(page.getByTestId('po-status')).toContainText('Approved')
  await page.getByRole('button', { name: 'Close' }).click()

  // receive: first part with one unit rejected (stays Approved), then the rest (Complete)
  await openPo(page, '2', number)
  await page.getByTestId('po-receive').click()
  const first = Math.ceil(ordered / 2)
  await page.getByRole('spinbutton', { name: /^Received for/ }).fill(String(first))
  await page.getByRole('spinbutton', { name: /^Rejected for/ }).fill('1')
  await shot(page, 'receive')
  await page.getByTestId('po-receive').click()
  await expect(page.getByRole('status').filter({ hasText: `${number} partially received` })).toBeVisible()
  await expect(page.getByTestId('line-received')).toHaveText(String(first))
  await page.getByTestId('po-receive').click()
  await page.getByRole('spinbutton', { name: /^Received for/ }).fill(String(ordered - first))
  await page.getByTestId('po-receive').click()
  await expect(page.getByRole('status').filter({ hasText: `${number} received in full` })).toBeVisible()
  await expect(page.getByTestId('po-status')).toContainText('Complete')
  await shot(page, 'po-complete')
  await page.getByRole('button', { name: 'Close' }).click()

  // replication monitor: create, approve and two receipts, each receipt with the stock movement (TransactionHistory P)
  await page.goto('./back-office/replication')
  const entries = page.getByTestId('feed-entry').filter({ hasText: number })
  await expect(entries.filter({ hasText: 'po.receive' }).first()).toContainText('type P')
  await expect(entries.filter({ hasText: 'po.receive' })).toHaveCount(2)
  await expect(entries.filter({ hasText: 'po.approve' })).toHaveCount(1)
  await expect(entries.filter({ hasText: 'po.create' })).toHaveCount(1)
  await shot(page, 'replication')

  // vendor page: performance tiles and the new PO in its history (PUR-05)
  await page.goto('./back-office/procurement/vendors')
  await page.getByLabel('Filter rows').fill(vendorName)
  await page.getByTestId('open-vendor').filter({ hasText: vendorName }).first().click()
  await expect(page.getByTestId('vendor-performance')).toContainText('Reject rate')
  await expect(page.getByTestId('vendor-pos')).toContainText(number)
  await shot(page, 'vendor')
  await page.getByRole('button', { name: 'Close' }).click()

})

test('procurement needs a buyer or purchasing manager role', async ({ page }) => {
  await setup(page)
  await signIn(page, 'fulfilment@adventure-works.com')
  await page.goto('./back-office/procurement')
  await expect(page.getByText('Back-office sign-in required')).toBeVisible()
  await expect(page.getByText('mikael0@adventure-works.com')).toBeVisible()
})

test('historical (SQL-era) purchase orders are read-only', async ({ page }) => {
  await setup(page)
  await signIn(page, MANAGER)
  await page.goto('./back-office/procurement/orders')
  await page.getByTestId('po-tab-1').click()
  const sql = page.getByRole('row').filter({ hasText: 'SQL-era, read-only' }).first()
  await expect(sql).toBeVisible({ timeout: 30_000 })
  await sql.getByTestId('open-po').click()
  await expect(page.getByRole('dialog')).toContainText('SQL-era · read-only')
  await expect(page.getByTestId('po-approve')).toHaveCount(0)
  await shot(page, 'historical-po')
})
