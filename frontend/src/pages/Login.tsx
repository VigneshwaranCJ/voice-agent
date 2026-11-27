import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try { await login(email, password); nav('/') } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-white p-5">
      {/* soft ambient gradient */}
      <div aria-hidden className="pointer-events-none absolute -top-40 left-1/2 h-[36rem] w-[60rem] -translate-x-1/2 rounded-full bg-gradient-to-r from-brand-100 via-violet-100 to-sky-100 opacity-70 blur-3xl" />
      <form onSubmit={submit} className="animate-rise relative w-full max-w-sm">
        <div className="mb-10 text-center">
          <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-[#8e5cf7] text-white">
            <svg viewBox="0 0 24 24" className="h-7 w-7" aria-hidden="true">
              <rect x="3" y="9" width="2.6" height="6" rx="1.3" fill="currentColor" />
              <rect x="7.6" y="5" width="2.6" height="14" rx="1.3" fill="currentColor" />
              <rect x="12.2" y="7.5" width="2.6" height="9" rx="1.3" fill="currentColor" />
              <rect x="16.8" y="3.5" width="2.6" height="17" rx="1.3" fill="currentColor" />
            </svg>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">Sign in to <span className="text-gradient">VoiceCare</span></h1>
          <p className="mt-3 text-base text-slate-500">Your AI customer-care agents, in one place.</p>
        </div>
        {error && <div role="alert" className="note note-red mb-4">{error}</div>}
        <div className="space-y-3">
          <input className="input h-12 text-base" placeholder="Email"aria-label="Email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input className="input h-12 text-base" type="password" placeholder="Password" aria-label="Password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <button className="btn mt-6 h-12 w-full text-base" disabled={busy || !email || !password}>{busy ? 'Signing in…' : 'Continue'}</button>
        <p className="mt-6 text-center text-sm text-slate-500">Development accounts are listed in <code>.env.example</code>.</p>
      </form>
    </div>
  )
}
