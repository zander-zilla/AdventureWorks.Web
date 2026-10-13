import { defineConfig } from '@playwright/test'

// C2-1 showcase E2E: the full static site from showcase/build.py (Chapter 2 at /, frozen Chapter 1 at /c1/), no AWS.
// Build first: npm run build:showcase && python3 ../../showcase/build.py. SHOWCASE_URL targets a deployed/running site.
const base = process.env.SHOWCASE_URL ?? 'http://localhost:4180/'
export default defineConfig({
  testDir: 'e2e-showcase',
  use: { baseURL: base, viewport: { width: 1440, height: 900 } },
  webServer: process.env.SHOWCASE_URL ? undefined
    : { command: 'python3 ../../showcase/serve.py --port 4180', url: base, reuseExistingServer: true },
})
