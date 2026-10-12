import { defineConfig } from '@playwright/test'

// E2E against the built bundle served by `vite preview` with /api/v2 mocked per test (no backend, no AWS).
// Set AW_E2E_BASE to run against a real app (e.g. http://localhost:5090/app/).
const base = process.env.AW_E2E_BASE ?? 'http://localhost:4173/app/'
export default defineConfig({
  testDir: 'e2e',
  use: { baseURL: base, viewport: { width: 1440, height: 900 } },
  webServer: process.env.AW_E2E_BASE ? undefined : { command: 'npx vite preview --port 4173 --strictPort', url: base, reuseExistingServer: true },
})
