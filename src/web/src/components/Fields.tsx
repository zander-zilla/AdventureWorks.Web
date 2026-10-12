import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'
import { cx } from './cx'

const control = 'w-full rounded-aw border border-line bg-bg px-3 py-2 text-ink placeholder:text-mute focus:border-accent focus:outline-none'

function Field({ label, hint, error, id, children }: { label: string; hint?: string; error?: string; id: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-mute">{label}</label>
      {children}
      {error ? <span id={`${id}-err`} className="text-xs text-danger">{error}</span> : hint && <span className="text-xs text-mute">{hint}</span>}
    </div>
  )
}
export function TextField({ label, hint, error, className, ...p }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string }) {
  const id = useId()
  return <Field {...{ label, hint, error, id }}><input id={id} aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined}
    {...p} className={cx(control, error && 'border-danger', className)} /></Field>
}
export function SelectField({ label, hint, error, options, ...p }: SelectHTMLAttributes<HTMLSelectElement> & { label: string; hint?: string; error?: string; options: { value: string; label: string }[] }) {
  const id = useId()
  return <Field {...{ label, hint, error, id }}><select id={id} {...p} className={control}>{options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>
}
export function Checkbox({ label, ...p }: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-[var(--aw-accent)]" {...p} />{label}</label>
}
