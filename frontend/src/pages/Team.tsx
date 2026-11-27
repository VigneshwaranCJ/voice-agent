import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Badge, Empty, ErrorNote, PageHeader, fmtDate } from '../components/ui'
import { Select } from '../components/Select'
import { useToast } from '../components/Toast'
import { useAuth } from '../hooks/useAuth'
import { api } from '../services/api'

interface Member {
  id: string; email: string; full_name: string; role: 'platform_admin' | 'tenant_admin' | 'tenant_agent'
  is_active: boolean; last_login_at: string | null; created_at: string
}

const ROLE_LABEL: Record<Member['role'], string> = {
  platform_admin: 'Platform admin', tenant_admin: 'Admin', tenant_agent: 'Staff (view & follow up)',
}
const MIN_PASSWORD = 12

/** A random password the admin can pass on; the person changes it after signing in. */
export function generatePassword(length = 16) {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
  const bytes = crypto.getRandomValues(new Uint32Array(length))
  return Array.from(bytes, (b) => chars[b % chars.length]).join('')
}

export default function Team() {
  const { user, tenants, tenantId } = useAuth()
  const toast = useToast()
  const isPlatform = user?.role === 'platform_admin'
  const isAdmin = isPlatform || user?.role === 'tenant_admin'
  // Platform admins can switch between the selected business's team and the platform admins.
  const [platformScope, setPlatformScope] = useState(isPlatform && !tenantId)
  const businessName = tenants.find((t) => t.id === tenantId)?.name ?? user?.tenant_name ?? 'this business'
  const scopeLabel = platformScope ? 'Platform admins' : businessName
  const roles: Member['role'][] = platformScope ? ['platform_admin'] : ['tenant_admin', 'tenant_agent']

  const [members, setMembers] = useState<Member[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    setError(null)
    try { setMembers(await api<Member[]>('/users', { noTenant: platformScope })) } catch (e) { setError((e as Error).message) }
  }, [platformScope])
  useEffect(() => { load() }, [load, tenantId])

  const call = async (path: string, init: Parameters<typeof api>[1], done: string) => {
    try { await api(path, { ...init, noTenant: platformScope }); toast(done); await load(); return true }
    catch (e) { toast((e as Error).message, 'error'); return false }
  }

  return (
    <div>
      <PageHeader eyebrow="Settings" title="Team" subtitle={`People who can sign in to ${scopeLabel}. Admins manage agents and the team; staff see calls and follow up on leads.`}
        actions={isPlatform && tenantId ? (
          <div className="seg">
            {[false, true].map((p) => (
              <button key={String(p)} aria-pressed={platformScope === p} onClick={() => setPlatformScope(p)} className="normal-case">
                {p ? 'Platform admins' : businessName}
              </button>
            ))}
          </div>
        ) : undefined} />
      <ErrorNote error={error} />
      {isAdmin && <AddMember key={platformScope ? 'platform' : 'business'} roles={roles} onAdd={(body) => call('/users', { method: 'POST', json: body }, `${body.email} added`)} />}
      <div className="card card-table">
        {!members ? <div className="p-6 text-sm text-slate-500">Loading…</div> : members.length ? (
          <table className="table table-stack">
            <thead><tr><th>Person</th><th>Role</th><th>Status</th><th>Last sign-in</th>{isAdmin && <th />}</tr></thead>
            <tbody>{members.map((m) => (
              <MemberRow key={m.id} m={m} isSelf={m.id === user?.id} isAdmin={isAdmin} roles={roles}
                onRole={(role) => call(`/users/${m.id}`, { method: 'PATCH', json: { role } }, `${m.email} is now ${ROLE_LABEL[role]}`)}
                onActive={(is_active) => call(`/users/${m.id}`, { method: 'PATCH', json: { is_active } }, `${m.email} ${is_active ? 'reactivated' : 'deactivated'}`)}
                onReset={(new_password) => call(`/users/${m.id}/reset-password`, { method: 'POST', json: { new_password } }, `Password reset for ${m.email}`)} />
            ))}</tbody>
          </table>
        ) : <div className="p-3"><Empty>No one here yet.</Empty></div>}
      </div>
      {isAdmin && !platformScope && <EmailAlerts key={tenantId ?? 'none'} />}
    </div>
  )
}

/** New leads and handoffs are emailed to the business's admins when the server has SMTP set up. */
function EmailAlerts() {
  const toast = useToast()
  const [status, setStatus] = useState<{ configured: boolean; recipients: string[] } | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api<{ configured: boolean; recipients: string[] }>('/notifications/email').then(setStatus).catch(() => setStatus(null)) }, [])
  if (!status) return null
  const test = async () => {
    setBusy(true)
    try { const r = await api<{ sent_to: string }>('/notifications/email/test', { method: 'POST' }); toast(`Test email sent to ${r.sent_to}`) }
    catch (e) { toast((e as Error).message, 'error') } finally { setBusy(false) }
  }
  return (
    <div className="card mt-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="card-title flex items-center gap-2">Email alerts
            <Badge tone={status.configured ? 'green' : 'gray'}>{status.configured ? 'on' : 'not set up'}</Badge></h2>
          <p className="card-desc max-w-xl">
            {status.configured
              ? <>Admins get an email when the agent captures a lead or hands a call to a person.{' '}
                  {status.recipients.length ? <>Sent to: {status.recipients.join(', ')}.</> : 'No active admins to email yet.'}</>
              : <>Set <code>SMTP_HOST</code>, <code>SMTP_FROM</code> (and usually <code>SMTP_USERNAME</code> / <code>SMTP_PASSWORD</code>) in the server's <code>.env</code> to email admins about new leads and handoffs. Any provider works, e.g. Zoho Mail.</>}
          </p>
        </div>
        {status.configured && <button className="btn-ghost" onClick={test} disabled={busy}>{busy ? 'Sending…' : 'Send me a test email'}</button>}
      </div>
    </div>
  )
}

function AddMember({ roles, onAdd }: { roles: Member['role'][]; onAdd: (b: { email: string; full_name: string; role: string; password: string }) => Promise<boolean> }) {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState<string>(roles[roles.length - 1])
  const [password, setPassword] = useState(generatePassword)
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    if (await onAdd({ email: email.trim(), full_name: name.trim(), role, password })) {
      setEmail(''); setName(''); setPassword(generatePassword())
    }
    setBusy(false)
  }
  return (
    <form onSubmit={submit} className="card mb-6 space-y-5">
      <h2 className="card-title">Add a person</h2>
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div><label className="label" htmlFor="tm-email">Email</label>
          <input id="tm-email" type="email" required className="input" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div><label className="label" htmlFor="tm-name">Name</label>
          <input id="tm-name" className="input" maxLength={200} value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div><label className="label" htmlFor="tm-role">Role</label>
          <Select id="tm-role" value={role} onChange={setRole} options={roles.map((r) => ({ value: r, label: ROLE_LABEL[r] }))} /></div>
        <div><label className="label" htmlFor="tm-pw">Temporary password</label>
          <div className="flex gap-2">
            <input id="tm-pw" className="input font-mono" required minLength={MIN_PASSWORD} value={password} onChange={(e) => setPassword(e.target.value)} />
            <button type="button" className="btn-ghost whitespace-nowrap" onClick={() => setPassword(generatePassword())}>New</button>
          </div>
          <p className="hint">Share it privately. They can change it from the account menu after signing in.</p></div>
      </div>
      <button className="btn" disabled={busy || !email.trim() || password.length < MIN_PASSWORD}>{busy ? 'Adding…' : 'Add person'}</button>
    </form>
  )
}

function MemberRow({ m, isSelf, isAdmin, roles, onRole, onActive, onReset }: {
  m: Member; isSelf: boolean; isAdmin: boolean; roles: Member['role'][]
  onRole: (r: Member['role']) => void; onActive: (a: boolean) => void; onReset: (pw: string) => Promise<boolean>
}) {
  const [resetting, setResetting] = useState<string | null>(null)
  return (
    <>
      <tr className={m.is_active ? '' : 'opacity-60'}>
        <td data-label="Person"><div className="font-medium text-slate-900">{m.full_name || m.email}{isSelf && <span className="ml-2 text-sm font-normal text-slate-500">(you)</span>}</div>
          {m.full_name && <div className="text-sm text-slate-500">{m.email}</div>}</td>
        <td data-label="Role">{isAdmin && !isSelf && roles.length > 1 ? (
          <Select label={`Role for ${m.email}`} size="sm" className="min-w-52" value={m.role} onChange={(r) => onRole(r as Member['role'])}
            options={roles.map((r) => ({ value: r, label: ROLE_LABEL[r] }))} />) : ROLE_LABEL[m.role]}</td>
        <td data-label="Status"><Badge tone={m.is_active ? 'green' : 'gray'}>{m.is_active ? 'active' : 'deactivated'}</Badge></td>
        <td data-label="Last sign-in" className="whitespace-nowrap text-slate-500">{m.last_login_at ? fmtDate(m.last_login_at) : 'Never'}</td>
        {isAdmin && <td className="whitespace-nowrap text-right">{!isSelf && (<span className="inline-flex gap-1.5">
          <button className="btn-ghost btn-sm" onClick={() => setResetting(resetting === null ? generatePassword() : null)}>Reset password</button>
          <button className={`btn-ghost btn-sm ${m.is_active ? 'text-rose-600' : ''}`}
            onClick={() => (!m.is_active || confirm(`Deactivate ${m.email}? They are signed out at once.`)) && onActive(!m.is_active)}>
            {m.is_active ? 'Deactivate' : 'Reactivate'}</button>
        </span>)}</td>}
      </tr>
      {resetting !== null && (
        <tr><td colSpan={5}>
          <form className="flex flex-wrap items-end gap-2 rounded-2xl bg-slate-50 p-3"
            onSubmit={async (e) => { e.preventDefault(); if (await onReset(resetting)) setResetting(null) }}>
            <div className="min-w-64 flex-1"><label className="label" htmlFor={`rp-${m.id}`}>New password for {m.email}</label>
              <input id={`rp-${m.id}`} className="input font-mono" minLength={MIN_PASSWORD} required value={resetting} onChange={(e) => setResetting(e.target.value)} /></div>
            <button type="button" className="btn-ghost" onClick={() => setResetting(generatePassword())}>New</button>
            <button className="btn" disabled={resetting.length < MIN_PASSWORD}>Set password</button>
            <button type="button" className="btn-ghost" onClick={() => setResetting(null)}>Cancel</button>
          </form>
        </td></tr>
      )}
    </>
  )
}
