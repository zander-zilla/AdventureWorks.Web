import type { ButtonHTMLAttributes } from 'react'
import { cx } from './cx'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
const styles: Record<Variant, string> = {
  primary: 'bg-accent text-accent-ink hover:brightness-110',
  secondary: 'border border-line bg-transparent text-ink hover:bg-raised',
  ghost: 'bg-transparent text-mute hover:text-ink hover:bg-raised',
  danger: 'bg-danger text-white hover:brightness-110',
}
export function Button({ variant = 'primary', size = 'md', className, ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md' }) {
  return <button type="button" {...p} className={cx('inline-flex items-center gap-2 rounded-aw font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed',
    size === 'sm' ? 'px-3 py-1.5 text-xs' : 'px-4 py-2 text-sm', styles[variant], className)} />
}
