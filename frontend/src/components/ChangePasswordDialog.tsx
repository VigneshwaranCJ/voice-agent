import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api } from '../services/api'
import { ErrorNote } from './ui'

const MIN_LENGTH = 12

/** Change the signed-in user's own password (POST /auth/change-password). */
export default function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const first = useRef<HTMLInputElement>(null)

  useEffect(() => {
    first.current?.focus()
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [onClose])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (next.length < MIN_LENGTH) return setError(`New password must be at least ${MIN_LENGTH} characters.`)
    if (next !== confirm) return setError('The new passwords do not match.')
    if (next === current) return setError('New password must be different from the current one.')
    setBusy(true)
    try {
      await api('/auth/change-password', { method: 'POST', json: { current_password: current, new_password: next } })
      setDone(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not change the password.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/30 p-4 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div role="dialog" aria-modal="true" aria-labelledby="change-password-title"
        className="glass animate-rise w-full max-w-md rounded-3xl p-6 shadow-[var(--shadow-float)] ring-1 ring-black/5">
        <h2 id="change-password-title" className="text-lg font-semibold tracking-tight text-slate-900">Change password</h2>
        {done ? (
          <>
            <p className="mt-3 text-sm text-slate-600">
              Your password has been changed. Use the new one next time you sign in.
              Sessions on other devices stay signed in until they expire.
            </p>
            <div className="mt-6 flex justify-end">
              <button className="btn" onClick={onClose}>Done</button>
            </div>
          </>
        ) : (
          <form onSubmit={submit} className="mt-4 space-y-4">
            <ErrorNote error={error} />
            <div>
              <label className="label" htmlFor="pw-current">Current password</label>
              <input ref={first} id="pw-current" type="password" className="input" autoComplete="current-password"
                value={current} onChange={(e) => setCurrent(e.target.value)} required />
            </div>
            <div>
              <label className="label" htmlFor="pw-new">New password</label>
              <input id="pw-new" type="password" className="input" autoComplete="new-password" minLength={MIN_LENGTH}
                value={next} onChange={(e) => setNext(e.target.value)} required />
              <p className="hint">At least {MIN_LENGTH} characters.</p>
            </div>
            <div>
              <label className="label" htmlFor="pw-confirm">Confirm new password</label>
              <input id="pw-confirm" type="password" className="input" autoComplete="new-password"
                value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn" disabled={busy}>{busy ? 'Saving…' : 'Change password'}</button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
