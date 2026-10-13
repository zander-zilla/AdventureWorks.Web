import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { mockApi } from './mockApi'

// C2-5 end to end: ask the data (example question -> generated SQL that passed the guard -> chart + table; guardrail block)
// and semantic product search. Mocked /api/v2 by default; against the real image (Ai__Mode=mock, no warehouse) when AW_E2E_BASE is set.
const real = !!process.env.AW_E2E_BASE
const shots = process.env.AW_SCREENSHOTS

async function shot(page: Page, name: string) {
  if (!shots) return
  fs.mkdirSync(shots, { recursive: true })
  await page.screenshot({ path: path.join(shots, `c2-5-${name}${real ? '-real' : ''}.png`), fullPage: true })
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

test('ask the data: example -> guarded SQL -> chart; guardrail blocks personal data', async ({ page }) => {
  test.setTimeout(120_000)
  await setup(page)
  await signIn(page, 'ops@adventure-works.com')
  await page.goto('./back-office/ask')
  await expect(page.getByTestId('ask-example').first()).toBeVisible({ timeout: 30_000 })
  await page.getByTestId('ask-example').filter({ hasText: /^Sales by channel$/ }).click()
  await expect(page.getByTestId('ask-sql')).toContainText('FROM dw.v_sales')
  await expect(page.getByTestId('ask-result')).toContainText('passed the guard')
  if (real) await expect(page.getByTestId('ask-error')).toContainText('No warehouse is connected')
  else {
    await expect(page.getByTestId('ask-chart').locator('.recharts-bar-rectangle').first()).toBeVisible()
    await expect(page.getByTestId('ask-table')).toContainText('Reseller')
  }
  await shot(page, 'ask-bar')
  if (!real) {
    await page.getByTestId('ask-example').filter({ hasText: /^Sales by calendar year$/ }).click()
    await expect(page.getByTestId('ask-chart').locator('.recharts-line-curve')).toBeVisible()
    await shot(page, 'ask-line')
  }
  await page.getByTestId('ask-input').fill('List customer email addresses')
  await page.getByTestId('ask-go').click()
  await expect(page.getByTestId('ask-blocked')).toContainText('guardrail')
  await expect(page.getByTestId('ask-sql')).toHaveCount(0)
  await shot(page, 'guardrail')
})

test('semantic search ranks products by meaning + keywords', async ({ page }) => {
  await setup(page)
  await page.goto('./shop/search')
  await page.getByTestId('search-input').fill('red road bike')
  await page.getByTestId('search-go').click()
  await expect(page.getByTestId('search-hit').first()).toContainText(/Road/, { timeout: 60_000 })
  await shot(page, 'semantic-search')
})

test('ask the data is for staff only', async ({ page }) => {
  await setup(page)
  await page.goto('./back-office/ask')
  await expect(page.getByTestId('ask-input')).toHaveCount(0)
})
