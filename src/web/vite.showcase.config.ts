import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// C2-1: the showcase is a second entry of the same workspace (reuses src/components + tokens). Relative base so the
// bundle works at / on CloudFront and from any local static server; showcase/build.py adds data/ and the frozen c1/.
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  build: { outDir: 'dist-showcase', emptyOutDir: true, sourcemap: false, rollupOptions: { input: 'showcase.html' } },
})
