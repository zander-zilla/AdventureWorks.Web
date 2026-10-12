// Mirror of the CSS tokens for code that needs raw values (charts) and for the gallery's token table.
export type ThemeName = 'dark' | 'light'
export const tokenNames = ['bg', 'panel', 'raised', 'ink', 'mute', 'line', 'accent', 'accent2', 'ok', 'warn', 'danger', 'info'] as const
export type TokenName = (typeof tokenNames)[number]
export const tokens: Record<ThemeName, Record<TokenName, string>> = {
  dark: { bg: '#0f1420', panel: '#171e2e', raised: '#1e2740', ink: '#e6ebf5', mute: '#8a94a8', line: '#263049',
    accent: '#6c7cff', accent2: '#2dd4bf', ok: '#22c55e', warn: '#f59e0b', danger: '#f87171', info: '#60a5fa' },
  light: { bg: '#f7f4ee', panel: '#ffffff', raised: '#efe9dd', ink: '#1f2a24', mute: '#6b7468', line: '#e6e0d4',
    accent: '#2f6b4f', accent2: '#d98c3a', ok: '#15803d', warn: '#b45309', danger: '#b91c1c', info: '#1d4ed8' },
}
/** Area default: back office + showcase dark, shop light (decision 2). */
export const defaultThemeFor = (path: string): ThemeName => (path.startsWith('/shop') ? 'light' : 'dark')
export const cssVar = (t: TokenName) => `var(--aw-${t})`
