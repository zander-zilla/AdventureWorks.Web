/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// ADR 0010: the SPA is served by the .NET app under /app/ (same origin as /api/v2 and the auth cookie).
export default defineConfig({
  base: '/app/',
  plugins: [react(), tailwindcss()],
  build: { outDir: 'dist', sourcemap: false },
  server: { proxy: { '/api': process.env.AW_API ?? 'http://localhost:5090' } },
  test: { environment: 'jsdom', globals: true, setupFiles: ['src/test/setup.ts'], include: ['src/**/*.test.{ts,tsx}'] },
})
