import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

const SHOTS = process.env.AW_SCREENSHOTS
const bp = JSON.parse(readFileSync('../../docs/business-processes/business-processes.json', 'utf8'))
const c2 = JSON.parse(readFileSync('../../docs/chapter-2/chapter2.json', 'utf8'))

// expected coverage, computed independently of the UI code
const before = new Set<string>(bp.processes.filter((p: { counts: { app_pages: number } }) => p.counts.app_pages > 0).map((p: { id: string }) => p.id))
const after = new Set(before)
for (const ph of c2.phases) for (const pg of ph.pages) for (const id of pg.processes) after.add(id)

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true })
}
function noErrors(page: Page) {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(String(e)))
  return errors
}

test('Story: findings → features → architecture delta, keyboard navigation', async ({ page }) => {
  const errors = noErrors(page)
  await page.goto('./')
  await expect(page).toHaveURL(/#\/c2\/story$/)
  await expect(page.getByRole('radio', { name: 'Chapter 2 · Extend & modernize' })).toHaveAttribute('aria-checked', 'true')
  await expect(page.getByRole('heading', { name: 'What Chapter 1 left on the table' })).toBeVisible()
  await expect(page.getByText(`${before.size} → ${after.size}`).first()).toBeVisible()
  await shot(page, 'c2-1-story-1-findings')
  await page.keyboard.press('ArrowRight')
  await expect(page.getByTestId('features').locator('li')).toHaveCount(8)
  await expect(page.getByTestId('coming-soon').first()).toBeVisible()
  await shot(page, 'c2-1-story-2-features')
  await page.getByRole('button', { name: 'Next →' }).click()
  await expect(page.getByTestId('delta')).toContainText('React 19')
  await shot(page, 'c2-1-story-3-architecture-delta')
  expect(errors).toEqual([])
})

test('Business processes: landscape, coverage tile, deep link opens a process', async ({ page }) => {
  const errors = noErrors(page)
  await page.goto('./#/c2/processes')
  await expect(page.getByRole('table')).toContainText(bp.processes[0].name)
  await expect(page.getByRole('table').locator('tbody tr')).toHaveCount(bp.processes.length)
  await expect(page.getByTestId('coverage-tile')).toContainText(`${before.size} → ${after.size}`)
  await expect(page.getByTestId('coming-soon').first()).toBeVisible()
  await shot(page, 'c2-1-business-processes')
  await page.goto('./#/c2/processes/procure-to-pay')
  await expect(page.getByRole('dialog')).toContainText('Procure')
  await expect(page.getByTestId('process-detail')).toBeVisible()
  await shot(page, 'c2-1-business-process-detail')
  await page.keyboard.press('Escape')
  await expect(page).toHaveURL(/#\/c2\/processes$/)
  expect(errors).toEqual([])
})

test('Back office placeholder, What changed, Ask the data are clearly marked', async ({ page }) => {
  await page.goto('./#/c2/back-office')
  await expect(page.getByText('Back office screens are coming soon')).toBeVisible()
  await expect(page.getByTestId('planned-screen').first()).toContainText('Coming soon · C2-2')
  await shot(page, 'c2-1-back-office')
  await page.getByRole('link', { name: /What changed/ }).click()
  await expect(page.getByRole('table', { name: 'API v2 endpoints' })).toContainText('/api/v2/products')
  await expect(page.getByTestId('adrs')).toContainText('0010')
  await expect(page.getByText('dw.vendor_performance')).toBeVisible()
  await shot(page, 'c2-1-what-changed')
  await page.getByRole('link', { name: /Ask the data/ }).click()
  await expect(page.getByText('Coming soon (optional C2-5)')).toBeVisible()
  await shot(page, 'c2-1-ask-the-data')
})

test('Chapter switch: Chapter 1 is the frozen v1.0-migration site under /c1/, deep links both ways', async ({ page }) => {
  const errors = noErrors(page)
  await page.goto('./#/c2/story')
  await page.getByRole('radio', { name: 'Chapter 1 · Migration' }).click()
  await expect(page).toHaveURL(/\/c1\/$/)
  await expect(page.getByRole('tab', { name: 'Presentation' })).toBeVisible()
  await expect(page.getByRole('tab')).toHaveCount(8)
  await shot(page, 'c2-1-c1-frozen-presentation')
  await page.goto('./#/c1/')
  await expect(page).toHaveURL(/\/c1\/$/)
  await page.goto('./#/c2/changes')
  await expect(page.getByRole('heading', { name: 'What changed' })).toBeVisible()
  expect(errors).toEqual([])
})

test('Light theme persists', async ({ page }) => {
  await page.goto('./#/c2/story')
  await page.getByTestId('theme-toggle').click()
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await shot(page, 'c2-1-story-light')
})
