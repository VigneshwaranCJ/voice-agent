import { useEffect, useState } from 'react'
import { useToast } from '../components/Toast'
import { Select } from '../components/Select'
import { Badge, Empty, ErrorNote, PageHeader, SuccessNote, fmtDate } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../hooks/useAuth'
import { api } from '../services/api'
import type { Tenant } from '../types'

export function BusinessProfile() {
  const { data, error, setData } = useApi<Record<string, any>>('/business-profile')
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const toast = useToast()
  const [hours, setHours] = useState<[string, string][]>([])
  useEffect(() => { if (data) setHours(Object.entries(data.operating_hours ?? {}) as [string, string][]) }, [data])
  if (!data) return <ErrorNote error={error} />
  const field = (k: string, label: string) => (
    <div><label className="label">{label}</label><input className="input" value={data[k] ?? ''} onChange={(e) => setData({ ...data, [k]: e.target.value })} /></div>
  )
  const save = async () => {
    setMsg(null); setErr(null)
    try {
      const operating_hours = Object.fromEntries(hours.map(([k, v]) => [k.trim(), v.trim()]).filter(([k, v]) => k && v))
      setData(await api('/business-profile', { method: 'PUT', json: { ...data, operating_hours } }))
      setMsg('Saved')
      toast('Business profile saved')
    } catch (e) { setErr((e as Error).message) }
  }
  return (
    <div>
      <PageHeader eyebrow="Settings" title="Business Profile" subtitle="Business context given to the agent on every call." />
      <ErrorNote error={err} />
      <SuccessNote>{msg}</SuccessNote>
      <div className="card grid grid-cols-1 gap-5 md:grid-cols-2">
        {field('display_name', 'Display name')}{field('phone', 'Phone')}{field('email', 'Email')}{field('website', 'Website')}{field('timezone', 'Timezone')}
        <div className="md:col-span-2"><label className="label">Description</label><textarea className="input h-24" value={data.description} onChange={(e) => setData({ ...data, description: e.target.value })} /></div>
        <div className="md:col-span-2"><label className="label">Services (comma separated)</label>
          <input className="input" value={(data.services ?? []).join(', ')} onChange={(e) => setData({ ...data, services: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} /></div>
        <div className="md:col-span-2"><HoursEditor rows={hours} onChange={setHours} /></div>
      </div>
      <div className="mt-5 flex justify-end"><button className="btn" onClick={save}>Save changes</button></div>
    </div>
  )
}

export function Integrations() {
  const { data, reload, error } = useApi<{ id: string; name: string; kind: string; permissions: string; last_tested_at: string | null; last_test_ok: boolean | null }[]>('/integrations/connections')
  const [form, setForm] = useState({ name: '', kind: 'postgresql', dsn: '', base_url: '', api_key: '', permissions: 'read' })
  const [result, setResult] = useState<Record<string, string>>({})
  const [err, setErr] = useState<string | null>(null)
  const create = async () => {
    setErr(null)
    const config = form.kind === 'rest_api' ? { base_url: form.base_url, api_key: form.api_key || undefined } : { dsn: form.dsn }
    try { await api('/integrations/connections', { method: 'POST', json: { name: form.name, kind: form.kind, permissions: form.permissions, config } }); setForm({ ...form, name: '', dsn: '', base_url: '', api_key: '' }); reload() }
    catch (e) { setErr((e as Error).message) }
  }
  const test = async (id: string) => {
    const r = await api<{ ok: boolean; message: string }>(`/integrations/connections/${id}/test`, { method: 'POST' })
    setResult({ ...result, [id]: `${r.ok ? '✓' : '✗'} ${r.message}` }); reload()
  }
  return (
    <div>
      <PageHeader eyebrow="Connections" title="Integrations" subtitle="Connect the business's own database or API. Credentials are encrypted at rest and never shown again." />
      <ErrorNote error={err || error} />
      <div className="card mb-6 grid grid-cols-1 gap-5 md:grid-cols-2">
        <div className="md:col-span-2"><h2 className="card-title">Add a connection</h2></div>
        <div><label className="label">Name</label><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
        <div><label className="label" htmlFor="ic-kind">Type</label><Select id="ic-kind" value={form.kind} onChange={(kind) => setForm({ ...form, kind })}
          options={[{ value: 'postgresql', label: 'PostgreSQL' }, { value: 'mysql', label: 'MySQL' }, { value: 'rest_api', label: 'REST API' }]} /></div>
        {form.kind === 'rest_api' ? (<>
          <div><label className="label">Base URL</label><input className="input" value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} /></div>
          <div><label className="label">API key (optional)</label><input className="input" type="password" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} /></div>
        </>) : (
          <div className="md:col-span-2"><label className="label">Connection string</label><input className="input font-mono" type="password" placeholder={form.kind === 'mysql' ? 'host/user/password via API' : 'postgresql://user:pass@host:5432/db'} value={form.dsn} onChange={(e) => setForm({ ...form, dsn: e.target.value })} /></div>
        )}
        <div><label className="label" htmlFor="ic-perm">Permissions</label><Select id="ic-perm" value={form.permissions} onChange={(permissions) => setForm({ ...form, permissions })}
          options={[{ value: 'read', label: 'Read only' }, { value: 'read_write', label: 'Read / write' }]} /></div>
        <div className="flex items-end"><button className="btn" disabled={!form.name} onClick={create}>Add connection</button></div>
      </div>
      <div className="card card-table">
        {data?.length ? (
          <table className="table table-stack"><thead><tr><th>Name</th><th>Type</th><th>Access</th><th>Last test</th><th></th></tr></thead>
            <tbody>{data.map((c) => (
              <tr key={c.id}><td data-label="Name" className="font-medium text-slate-900">{c.name}</td><td data-label="Type">{c.kind}</td><td data-label="Access">{c.permissions.replace('_', ' / ')}</td>
                <td data-label="Last test">{c.last_test_ok == null ? '—' : <Badge tone={c.last_test_ok ? 'green' : 'red'}>{c.last_test_ok ? 'ok' : 'failed'}</Badge>} <span className="text-xs text-slate-500">{fmtDate(c.last_tested_at)}</span>
                  {result[c.id] && <div className="mt-1 text-sm text-slate-500">{result[c.id]}</div>}</td>
                <td className="text-right"><button className="btn-ghost btn-sm" onClick={() => test(c.id)}>Test</button></td></tr>
            ))}</tbody></table>
        ) : <div className="p-3"><Empty>No external connections. Demo businesses use the platform's built-in tables.</Empty></div>}
      </div>
    </div>
  )
}

export function Tenants() {
  const { data, reload, error } = useApi<Tenant[]>('/tenants')
  const { refreshTenants } = useAuth()
  const { data: ind } = useApi<{ available: { key: string; label: string }[]; planned: { key: string; label: string }[] }>('/industries')
  const [f, setF] = useState({ name: '', slug: '', industry: 'custom', admin_email: '', admin_password: '' })
  const [err, setErr] = useState<string | null>(null)
  const create = async () => {
    setErr(null)
    try {
      await api('/tenants', { method: 'POST', json: { ...f, admin_email: f.admin_email || null, admin_password: f.admin_password || null } })
      setF({ name: '', slug: '', industry: 'custom', admin_email: '', admin_password: '' }); reload()
      await refreshTenants() // the account menu's business switcher picks it up (and selects it if none was)
    } catch (e) { setErr((e as Error).message) }
  }
  return (
    <div>
      <PageHeader eyebrow="Platform" title="All Businesses" subtitle="Onboard a business without code changes. Then create its agent under Agents." />
      <ErrorNote error={err || error} />
      <div className="card mb-6 grid grid-cols-1 gap-5 md:grid-cols-2">
        <div className="md:col-span-2"><h2 className="card-title">Add a business</h2></div>
        <div><label className="label">Business name</label><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value, slug: e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') })} /></div>
        <div><label className="label">Slug</label><input className="input" value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value })} /></div>
        <div><label className="label" htmlFor="tn-industry">Industry</label><Select id="tn-industry" value={f.industry} onChange={(industry) => setF({ ...f, industry })}
          options={[...(ind?.available ?? []).map((i) => ({ value: i.key, label: i.label })),
            ...(ind?.planned ?? []).map((i) => ({ value: i.key, label: `${i.label} (uses custom module for now)` }))]} /></div>
        <div />
        <div><label className="label">Admin email (optional)</label><input className="input" value={f.admin_email} onChange={(e) => setF({ ...f, admin_email: e.target.value })} /></div>
        <div><label className="label">Admin password (min 8)</label><input className="input" type="password" value={f.admin_password} onChange={(e) => setF({ ...f, admin_password: e.target.value })} /></div>
        <div className="flex items-end"><button className="btn" disabled={!f.name || !f.slug} onClick={create}>Create business</button></div>
      </div>
      <div className="card card-table">{data?.length ? (
        <table className="table table-stack"><thead><tr><th>Name</th><th>Industry</th><th>Slug</th><th>Created</th></tr></thead>
          <tbody>{data.map((t) => <tr key={t.id}><td data-label="Name" className="font-medium text-slate-900">{t.name}</td><td data-label="Industry"><span className="capitalize">{t.industry.replace(/_/g, ' ')}</span></td><td data-label="Slug" className="font-mono text-[13px]">{t.slug}</td><td data-label="Created" className="whitespace-nowrap text-slate-500">{fmtDate(t.created_at)}</td></tr>)}</tbody></table>
      ) : <div className="p-3"><Empty>No businesses.</Empty></div>}</div>
    </div>
  )
}

const HOURS_PRESETS: Record<string, [string, string][]> = {
  'Mon–Sat, Sunday closed': [['Mon-Sat', '9:30 AM - 6:30 PM'], ['Sunday', 'Closed']],
  'Mon–Fri, weekends closed': [['Mon-Fri', '9:00 AM - 6:00 PM'], ['Sat-Sun', 'Closed']],
  'Open every day': [['Mon-Sun', '9:00 AM - 9:00 PM']],
  'Hospital (OPD + 24×7 emergency)': [['OPD Mon-Sat', '9:00 AM - 6:00 PM'], ['Emergency', '24 x 7']],
}

/** Opening hours as label → hours rows (stored as a JSON object the agent reads on every call). */
function HoursEditor({ rows, onChange }: { rows: [string, string][]; onChange: (r: [string, string][]) => void }) {
  const set = (i: number, j: 0 | 1, v: string) => onChange(rows.map((r, k) => (k === i ? (j ? [r[0], v] : [v, r[1]]) : r)))
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="label mb-0">Opening hours</span>
        <Select label="Fill from a preset" size="sm" className="w-auto" value="" placeholder="Fill from a preset…"
          onChange={(k) => onChange(HOURS_PRESETS[k])} options={Object.keys(HOURS_PRESETS).map((k) => ({ value: k, label: k }))} />
      </div>
      <div className="space-y-2">
        {rows.map(([day, time], i) => (
          <div key={i} className="flex gap-2">
            <input aria-label="Days" className="input w-44" placeholder="e.g. Mon-Sat" value={day} onChange={(e) => set(i, 0, e.target.value)} />
            <input aria-label="Hours" className="input" placeholder="e.g. 9:30 AM - 6:30 PM, or Closed" value={time} onChange={(e) => set(i, 1, e.target.value)} />
            <button type="button" className="btn-ghost shrink-0" aria-label={`Remove ${day || 'row'}`} onClick={() => onChange(rows.filter((_, k) => k !== i))}>Remove</button>
          </div>
        ))}
        {!rows.length && <p className="text-sm text-slate-500">No hours set. The agent will say it doesn't know your timings.</p>}
        <button type="button" className="btn-ghost btn-sm" onClick={() => onChange([...rows, ['', '']])}>+ Add row</button>
      </div>
    </div>
  )
}
