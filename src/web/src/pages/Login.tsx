import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { useAuth } from '../api/auth'
import { ApiError } from '../api/client'
import { Button, PageHeader, TextField } from '../components'

export function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('donald0@adventure-works.com')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string>()
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setError(undefined)
    try { await login(email, password); nav('/') } catch (x) { setError(x instanceof ApiError && x.status === 401 ? 'Unknown email or wrong password' : 'Sign-in failed') }
  }
  return (
    <div className="max-w-sm">
      <PageHeader title="Sign in" sub="Demo customers share one password (see README)." />
      <form onSubmit={submit} className="flex flex-col gap-4 rounded-aw border border-line bg-panel p-5">
        <TextField label="Email" type="email" value={email} onChange={e => setEmail(e.target.value)} required autoComplete="username" />
        <TextField label="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} required error={error} autoComplete="current-password" />
        <Button type="submit">Sign in</Button>
      </form>
    </div>
  )
}
