import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { AppShell, ChapterSwitch, DataTable, Drawer, KpiCard, StatusPill, TextField, ToastProvider, useToast, orderStatus, sortRows, filterRows, type Column } from '.'
import { ThemeProvider } from '../theme/ThemeProvider'
import { defaultThemeFor, tokens, tokenNames } from '../theme/tokens'

type R = { id: string; name: string; n: number }
const rows: R[] = [{ id: 'a', name: 'Road-150', n: 3 }, { id: 'b', name: 'Mountain-200', n: 1 }, { id: 'c', name: 'Touring-1000', n: 2 }]
const cols: Column<R>[] = [{ key: 'name', header: 'Name', value: r => r.name }, { key: 'n', header: 'N', value: r => r.n, align: 'right' }]

describe('tokens', () => {
  it('both themes define every token', () => { for (const t of ['dark', 'light'] as const) for (const k of tokenNames) expect(tokens[t][k]).toMatch(/^#[0-9a-f]{6}$/) })
  it('shop defaults light, everything else dark', () => { expect(defaultThemeFor('/shop/products')).toBe('light'); expect(defaultThemeFor('/design')).toBe('dark') })
})

describe('DataTable', () => {
  it('sorts and filters (pure helpers)', () => {
    expect(sortRows(rows, cols[1], 'asc').map(r => r.id)).toEqual(['b', 'c', 'a'])
    expect(sortRows(rows, cols[0], 'desc').map(r => r.id)).toEqual(['c', 'a', 'b'])
    expect(filterRows(rows, cols, 'mount').map(r => r.id)).toEqual(['b'])
  })
  it('sorts by header click, filters and multi-selects', async () => {
    const u = userEvent.setup(), onSel = vi.fn()
    render(<DataTable rows={rows} columns={cols} rowKey={r => r.id} selectable onSelectionChange={onSel} />)
    await u.click(screen.getByRole('button', { name: 'N' }))
    const names = () => screen.getAllByRole('row').slice(1).map(r => within(r).getAllByRole('cell')[1].textContent)
    expect(names()).toEqual(['Mountain-200', 'Touring-1000', 'Road-150'])
    await u.click(screen.getByRole('button', { name: /N ↑/ }))
    expect(names()[0]).toBe('Road-150')
    await u.click(screen.getByLabelText('Select all'))
    expect(onSel).toHaveBeenLastCalledWith(['a', 'c', 'b'])
    expect(screen.getByTestId('selected-count')).toHaveTextContent('3 selected')
    await u.type(screen.getByLabelText('Filter rows'), 'zzz')
    expect(screen.getByText('No rows')).toBeInTheDocument()
  })
})

describe('small components', () => {
  it('StatusPill maps all 6 order statuses', () => { expect(Object.keys(orderStatus)).toHaveLength(6); render(<StatusPill label="Shipped" tone="ok" />); expect(screen.getByText('Shipped')).toHaveClass('text-ok') })
  it('KpiCard shows a down trend', () => { render(<KpiCard label="Backordered" value="27" delta="3" trend="down" />); expect(screen.getByText(/▼/)).toHaveClass('text-danger') })
  it('TextField wires label and error', () => { render(<TextField label="Qty" error="Must be at least 1" />); expect(screen.getByLabelText('Qty')).toHaveAttribute('aria-invalid', 'true'); expect(screen.getByLabelText('Qty')).toHaveAccessibleDescription('Must be at least 1') })
  it('ChapterSwitch is a radio group', async () => {
    const f = vi.fn(); render(<ChapterSwitch value="c2" onChange={f} />)
    expect(screen.getByRole('radio', { name: /Chapter 2/ })).toHaveAttribute('aria-checked', 'true')
    await userEvent.click(screen.getByRole('radio', { name: /Chapter 1/ })); expect(f).toHaveBeenCalledWith('c1')
  })
  it('Drawer closes on Escape', async () => {
    const f = vi.fn(); render(<Drawer open title="Ship" onClose={f}>x</Drawer>)
    expect(screen.getByRole('dialog', { name: 'Ship' })).toBeInTheDocument(); await userEvent.keyboard('{Escape}'); expect(f).toHaveBeenCalled()
  })
  it('Toast shows a message', async () => {
    const B = () => { const t = useToast(); return <button onClick={() => t('Saved', 'ok')}>go</button> }
    render(<ToastProvider><B /></ToastProvider>); await userEvent.click(screen.getByText('go')); expect(screen.getByText('Saved')).toBeInTheDocument()
  })
})

describe('AppShell + theme', () => {
  it('toggles and persists the theme on <html>', async () => {
    localStorage.clear()
    render(<MemoryRouter><ThemeProvider><AppShell nav={[{ title: 'Overview', items: [{ to: '/', label: 'Home', icon: '◧' }] }]} chapter="c2" onChapter={() => {}}>body</AppShell></ThemeProvider></MemoryRouter>)
    expect(document.documentElement.dataset.theme).toBe('dark')
    await userEvent.click(screen.getByTestId('theme-toggle'))
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('aw.theme')).toBe('light')
    expect(screen.getByRole('navigation', { name: 'Main' })).toHaveTextContent('Home')
  })
})
