# AdventureWorks Chapter 2 front end (`src/web`)

React 19 + TypeScript + Vite + Tailwind CSS v4 ([ADR 0010](../../docs/adr/0010-chapter-2-front-end.md)). Served by the
.NET 10 app under **`/app/`**; talks to **`/api/v2`** on the same origin with the app's cookie auth.

```bash
npm ci
npm run dev          # http://localhost:5173/app/ – proxies /api to AW_API (default http://localhost:5090, scripts/after-up.sh)
npm run lint && npm run typecheck && npm test   # ESLint, tsc, Vitest
npm run build        # dist/ (the Docker image copies it to wwwroot/app)
npx playwright test  # e2e on `vite preview` with /api/v2 mocked; AW_SCREENSHOTS=dir saves screenshots
AW_E2E_BASE=http://localhost:5090/app/ npx playwright test   # against the real app
```

- Tokens: `src/index.css` (`[data-theme=dark]` = B · Ops console, `[data-theme=light]` = A · Trail), mirrored in `src/theme/tokens.ts`.
  Components use only semantic utilities (`bg-panel`, `text-mute`, `border-line`, `rounded-aw`, …), never raw colours.
- Components: `src/components` (AppShell, ChapterSwitch, NavRail, KpiCard, DataTable, StatusPill, Drawer, Fields, Toast,
  EmptyState, Chart, Timeline). Gallery: `/app/design`.
- API client: `src/api/client.ts` (sends `X-AW-Client`, required by the server on POST/PUT/DELETE).
