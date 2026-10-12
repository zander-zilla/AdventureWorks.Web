import { cx } from './cx'

export type Chapter = 'c1' | 'c2'
/** Header switch between the frozen Chapter 1 showcase (/c1/, built from v1.0-migration) and Chapter 2. */
export function ChapterSwitch({ value, onChange }: { value: Chapter; onChange: (c: Chapter) => void }) {
  const opt = (c: Chapter, label: string) => (
    <button type="button" role="radio" aria-checked={value === c} onClick={() => onChange(c)}
      className={cx('rounded-full px-3.5 py-1.5 text-xs font-medium', value === c ? 'bg-accent text-accent-ink' : 'text-mute hover:text-ink')}>{label}</button>)
  return <div role="radiogroup" aria-label="Chapter" className="flex rounded-full border border-line p-0.5">{opt('c1', 'Chapter 1 · Migration')}{opt('c2', 'Chapter 2 · Extend & modernize')}</div>
}
