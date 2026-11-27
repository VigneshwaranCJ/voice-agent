import { Fragment, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Badge, Empty, ErrorNote, PageHeader, fmtDate } from '../components/ui'
import { Select } from '../components/Select'
import { useToast } from '../components/Toast'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'
import { downloadCsv } from '../services/csv'

interface Lead {
  id: string; name: string; phone: string | null; interest: string; budget: string | null; location_preference: string | null
  status: string; assigned_to: string | null; notes: string; conversation_id: string | null; at: string
}
interface Escalation {
  id: string; conversation_id: string; reason: string; priority: string; summary: string
  status: string; assigned_to: string | null; notes: string; at: string
}
interface Member { id: string; email: string; full_name: string; is_active: boolean }

const LEAD_STATUSES = ['new', 'qualified', 'contacted', 'won', 'lost'] as const
const ESC_STATUSES = ['open', 'assigned', 'resolved'] as const
const statusOptions = (list: readonly string[]) => list.map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1) }))


export default function FollowUps() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'escalations' ? 'escalations' : 'leads'
  const { data: team } = useApi<Member[]>('/users')
  const people = (team ?? []).filter((m) => m.is_active).map((m) => m.full_name || m.email)
  return (
    <div>
      <PageHeader eyebrow="Activity" title="Follow-ups" subtitle="Leads the agent captured and calls it handed to a person. Assign them, track progress, keep notes."
        actions={
          <div className="seg">
            {(['leads', 'escalations'] as const).map((t) => (
              <button key={t} aria-pressed={tab === t} onClick={() => setParams(t === 'leads' ? {} : { tab: t })}>{t}</button>
            ))}
          </div>
        } />
      {tab === 'leads' ? <Leads people={people} /> : <Escalations people={people} />}
    </div>
  )
}

function useFilter<T extends { status: string }>(rows: T[] | null, statuses: readonly string[], search: (r: T) => string) {
  const [status, setStatus] = useState('all')
  const [q, setQ] = useState('')
  const counts = useMemo(() => Object.fromEntries(statuses.map((s) => [s, rows?.filter((r) => r.status === s).length ?? 0])), [rows, statuses])
  const shown = useMemo(() => (rows ?? []).filter((r) => (status === 'all' || r.status === status)
    && (!q.trim() || search(r).toLowerCase().includes(q.trim().toLowerCase()))), [rows, status, q, search])
  const bar = (onExport: () => void) => (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      {['all', ...statuses].map((s) => (
        <button key={s} onClick={() => setStatus(s)} aria-pressed={status === s} className="chip">
          {s}{s !== 'all' && <span className="tabular-nums opacity-60">{counts[s]}</span>}
        </button>
      ))}
      <input aria-label="Search" type="search" className="input input-sm w-full sm:ml-auto sm:w-60" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
      <button className="btn-ghost btn-sm" onClick={onExport} disabled={!shown.length}>Export CSV</button>
    </div>
  )
  return { shown, bar }
}

function AssigneeSelect({ value, people, onChange, label }: { value: string | null; people: string[]; onChange: (v: string | null) => void; label: string }) {
  const options = value && !people.includes(value) ? [value, ...people] : people
  return (
    <Select label={label} size="sm" className="min-w-40" value={value ?? ''} onChange={(v) => onChange(v || null)}
      options={[{ value: '', label: 'Unassigned' }, ...options.map((p) => ({ value: p, label: p }))]} />
  )
}

function Notes({ value, onSave }: { value: string; onSave: (v: string) => Promise<void> }) {
  const [text, setText] = useState(value)
  const [busy, setBusy] = useState(false)
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
      <textarea aria-label="Notes" className="input h-24 flex-1" placeholder="Called back, interested in a site visit on Saturday…" maxLength={4000}
        value={text} onChange={(e) => setText(e.target.value)} />
      <button className="btn" disabled={busy || text === value} onClick={async () => { setBusy(true); await onSave(text); setBusy(false) }}>
        {busy ? 'Saving…' : 'Save notes'}</button>
    </div>
  )
}

function Leads({ people }: { people: string[] }) {
  const { data, error, setData } = useApi<Lead[]>('/leads')
  const toast = useToast()
  const [open, setOpen] = useState<string | null>(null)
  const { shown, bar } = useFilter(data, LEAD_STATUSES, (r) => `${r.name} ${r.phone ?? ''} ${r.interest} ${r.assigned_to ?? ''} ${r.notes}`)
  const patch = async (lead: Lead, body: Partial<Pick<Lead, 'status' | 'assigned_to' | 'notes'>>, done: string) => {
    try {
      const updated = await api<Lead>(`/leads/${lead.id}`, { method: 'PATCH', json: body })
      setData((rows) => rows?.map((r) => (r.id === lead.id ? updated : r)) ?? null)
      toast(done)
    } catch (e) { toast((e as Error).message, 'error') }
  }
  const exportCsv = () => downloadCsv('leads', ['Created', 'Name', 'Phone', 'Interest', 'Budget', 'Location', 'Status', 'Assigned to', 'Notes'],
    shown.map((r) => [r.at, r.name, r.phone, r.interest, r.budget, r.location_preference, r.status, r.assigned_to, r.notes]))
  return (
    <>
      <ErrorNote error={error} />
      {bar(exportCsv)}
      <div className="card card-table">
        {!data ? <div className="p-6 text-sm text-slate-500">Loading…</div> : shown.length ? (
          <table className="table table-stack">
            <thead><tr><th>Created</th><th>Lead</th><th>Interest</th><th>Status</th><th>Assigned to</th><th /></tr></thead>
            <tbody>{shown.map((r) => (<Fragment key={r.id}>
              <tr>
                <td data-label="Created" className="whitespace-nowrap text-slate-500">{fmtDate(r.at)}</td>
                <td data-label="Lead"><div className="font-medium text-slate-900">{r.name || 'Unnamed'}</div>
                  {r.phone && <a className="text-sm text-brand-600 hover:underline" href={`tel:${r.phone}`}>{r.phone}</a>}</td>
                <td data-label="Interest" className="max-w-xs text-slate-600">{r.interest || '—'}{r.budget && <div className="text-sm text-slate-500">Budget {r.budget}</div>}</td>
                <td data-label="Status"><Select label={`Status of ${r.name}`} size="sm" className="min-w-36" value={r.status}
                  onChange={(status) => patch(r, { status }, `${r.name || 'Lead'} marked ${status}`)} options={statusOptions(LEAD_STATUSES)} /></td>
                <td data-label="Assigned to"><AssigneeSelect label={`Assignee for ${r.name}`} value={r.assigned_to} people={people}
                  onChange={(v) => patch(r, { assigned_to: v }, v ? `Assigned to ${v}` : 'Unassigned')} /></td>
                <td className="whitespace-nowrap text-right">
                  <span className="inline-flex gap-1.5"><button className="btn-ghost btn-sm" onClick={() => setOpen(open === r.id ? null : r.id)}>{r.notes ? 'Notes •' : 'Notes'}</button>
                  {r.conversation_id && <Link className="btn-ghost btn-sm" to={`/calls/${r.conversation_id}`}>Call</Link>}</span>
                </td>
              </tr>
              {open === r.id && <tr><td colSpan={6}><Notes value={r.notes} onSave={(notes) => patch(r, { notes }, 'Notes saved')} /></td></tr>}
            </Fragment>))}</tbody>
          </table>
        ) : <div className="p-3"><Empty>{data.length ? 'No leads match this filter.' : 'No leads yet. The agent creates them when a caller asks to be contacted.'}</Empty></div>}
      </div>
    </>
  )
}

function Escalations({ people }: { people: string[] }) {
  const { data, error, setData } = useApi<Escalation[]>('/escalations')
  const toast = useToast()
  const [open, setOpen] = useState<string | null>(null)
  const { shown, bar } = useFilter(data, ESC_STATUSES, (r) => `${r.reason} ${r.summary} ${r.assigned_to ?? ''} ${r.notes}`)
  const patch = async (esc: Escalation, body: Partial<Pick<Escalation, 'status' | 'assigned_to' | 'notes'>>, done: string) => {
    try {
      const updated = await api<Escalation>(`/escalations/${esc.id}`, { method: 'PATCH', json: body })
      setData((rows) => rows?.map((r) => (r.id === esc.id ? updated : r)) ?? null)
      toast(done)
    } catch (e) { toast((e as Error).message, 'error') }
  }
  const exportCsv = () => downloadCsv('escalations', ['Created', 'Priority', 'Reason', 'Summary', 'Status', 'Assigned to', 'Notes'],
    shown.map((r) => [r.at, r.priority, r.reason, r.summary, r.status, r.assigned_to, r.notes]))
  return (
    <>
      <ErrorNote error={error} />
      {bar(exportCsv)}
      <div className="card card-table">
        {!data ? <div className="p-6 text-sm text-slate-500">Loading…</div> : shown.length ? (
          <table className="table table-stack">
            <thead><tr><th>Created</th><th>Why</th><th>Summary</th><th>Status</th><th>Assigned to</th><th /></tr></thead>
            <tbody>{shown.map((r) => (<Fragment key={r.id}>
              <tr>
                <td data-label="Created" className="whitespace-nowrap text-slate-500">{fmtDate(r.at)}</td>
                <td data-label="Why"><div className="mb-1 font-medium capitalize text-slate-900">{r.reason.replace(/_/g, ' ')}</div>
                  <Badge tone={r.priority === 'critical' ? 'red' : r.priority === 'high' ? 'amber' : 'gray'}>{r.priority}</Badge></td>
                <td data-label="Summary" className="max-w-sm text-slate-600">{r.summary || '—'}</td>
                <td data-label="Status"><Select label={`Status of escalation ${r.reason}`} size="sm" className="min-w-36" value={r.status}
                  onChange={(status) => patch(r, { status }, `Marked ${status}`)} options={statusOptions(ESC_STATUSES)} /></td>
                <td data-label="Assigned to"><AssigneeSelect label={`Assignee for escalation ${r.reason}`} value={r.assigned_to} people={people}
                  onChange={(v) => patch(r, { assigned_to: v }, v ? `Assigned to ${v}` : 'Unassigned')} /></td>
                <td className="whitespace-nowrap text-right">
                  <span className="inline-flex gap-1.5"><button className="btn-ghost btn-sm" onClick={() => setOpen(open === r.id ? null : r.id)}>{r.notes ? 'Notes •' : 'Notes'}</button>
                  <Link className="btn-ghost btn-sm" to={`/calls/${r.conversation_id}`}>Call</Link></span>
                </td>
              </tr>
              {open === r.id && <tr><td colSpan={6}><Notes value={r.notes} onSave={(notes) => patch(r, { notes }, 'Notes saved')} /></td></tr>}
            </Fragment>))}</tbody>
          </table>
        ) : <div className="p-3"><Empty>{data.length ? 'No escalations match this filter.' : 'No escalations. The agent hands a call to a person when the caller asks or it cannot help.'}</Empty></div>}
      </div>
    </>
  )
}

