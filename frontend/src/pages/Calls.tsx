import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DateRangePicker } from '../components/DatePicker'
import { Select } from '../components/Select'
import { useToast } from '../components/Toast'
import { downloadCsv } from '../services/csv'
import { todayKey } from '../services/dates'
import { Badge, Empty, ErrorNote, Icons, PageHeader, fmtDate, statusTone } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../hooks/useAuth'
import { api } from '../services/api'
import { LANGUAGES, type Conversation, type Message } from '../types'

const PAGE = 100
const STATUSES = ['all', 'completed', 'escalated', 'abandoned', 'active'] as const
const CHANNELS = [
  { value: '', label: 'All channels' }, { value: 'sarvam_voice', label: 'Sarvam voice' }, { value: 'web_text', label: 'Web text' },
  { value: 'widget', label: 'Website widget' }, { value: 'phone', label: 'Phone' },
]

export function Calls() {
  const { tenantId } = useAuth()
  const toast = useToast()
  const [status, setStatus] = useState<string>('all')
  const [channel, setChannel] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('') // debounced search
  const [data, setData] = useState<Conversation[] | null>(null)
  const [more, setMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { const t = window.setTimeout(() => setQuery(q.trim()), 350); return () => window.clearTimeout(t) }, [q])

  const params = (offset: number) => {
    const u = new URLSearchParams({ limit: String(PAGE), offset: String(offset) })
    if (status !== 'all') u.set('status', status)
    if (channel) u.set('channel', channel)
    if (query) u.set('q', query)
    if (from) u.set('date_from', new Date(`${from}T00:00:00`).toISOString())
    if (to) u.set('date_to', new Date(new Date(`${to}T00:00:00`).getTime() + 86400000).toISOString()) // include the whole day
    return u.toString()
  }
  const load = async (offset = 0) => {
    setError(null)
    try {
      const rows = await api<Conversation[]>(`/conversations?${params(offset)}`)
      setData((d) => (offset ? [...(d ?? []), ...rows] : rows))
      setMore(rows.length === PAGE)
    } catch (e) { setError((e as Error).message) }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setData(null); load(0) }, [status, channel, query, from, to, tenantId])

  const exportCsv = () => {
    if (!data?.length) return
    downloadCsv('calls', ['Started', 'Ended', 'Channel', 'Status', 'Languages', 'Intents', 'Summary'],
      data.map((c) => [c.created_at, c.ended_at, c.channel, c.status, c.languages_used.map((l) => LANGUAGES[l] ?? l).join(' / '), c.intents.join(' / '), c.summary]))
    toast(`Exported ${data.length} calls`)
  }
  const filtered = status !== 'all' || channel || query || from || to
  const { data: escalations } = useApi<{ id: string; conversation_id: string; reason: string; priority: string; summary: string; status: string; at: string }[]>('/escalations?status=open')
  return (
    <div>
      <PageHeader eyebrow="Activity" title="Calls & Transcripts" subtitle="Every conversation, with what the agent did and why." />
      <ErrorNote error={error} />
      {!!escalations?.length && (
        <div className="card mb-6 overflow-hidden bg-gradient-to-br from-rose-50/70 to-white p-0">
          <div className="flex flex-wrap items-center gap-3 px-5 pb-2 pt-5 sm:px-6">
            <span className="icon-tile bg-gradient-to-br from-[#fb7185] to-[#e11d48] text-[#e11d48]"><span className="text-white">{Icons.alert}</span></span>
            <div className="min-w-0 flex-1 basis-40">
              <div className="card-title">Open escalations</div>
              <div className="text-sm text-slate-500">{escalations.length} waiting for a human</div>
            </div>
            <Link to="/follow-ups?tab=escalations" className="btn-ghost btn-sm">Assign & resolve</Link>
          </div>
          <div className="px-3 pb-3">
            {escalations.map((e) => (
              <Link key={e.id} to={`/calls/${e.conversation_id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-2xl px-2 py-2.5 text-sm transition hover:bg-white sm:flex-nowrap sm:px-3">
                <Badge tone={e.priority === 'critical' ? 'red' : 'amber'}>{e.priority}</Badge>
                <span className="whitespace-nowrap font-medium capitalize text-slate-900">{e.reason.replace(/_/g, ' ')}</span>
                {/* phones: summary on its own line under the badge and reason; wider: inline, truncated */}
                <span className="order-last min-w-0 basis-full truncate text-slate-500 sm:order-none sm:flex-1 sm:basis-auto">{e.summary}</span>
                <span className="ml-auto whitespace-nowrap text-xs text-slate-500">{fmtDate(e.at)}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
      {/* One filter row; on narrower screens it wraps and the search box fills its line. */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Status" className="flex flex-wrap items-center gap-1.5">
          {STATUSES.map((st) => (
            <button key={st} onClick={() => setStatus(st)} aria-pressed={status === st} className="chip px-3">{st}</button>
          ))}
        </div>
        <Select label="Channel" size="sm" className="w-auto min-w-36" value={channel} onChange={setChannel} options={CHANNELS} />
        <DateRangePicker size="sm" label="Call dates" value={{ from, to }} max={todayKey()}
          onChange={(r) => { setFrom(r.from); setTo(r.to) }} />
        <input aria-label="Search calls" type="search" className="input input-sm min-w-36 flex-1" placeholder="Search transcripts…" title="Searches call summaries and transcripts" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn-ghost btn-sm" onClick={exportCsv} disabled={!data?.length}>Export CSV</button>
      </div>
      <div className="card card-table">
        {!data ? <div className="p-6 text-sm text-slate-500">Loading…</div> : data.length ? (
          <table className="table table-stack">
            <thead><tr><th>Started</th><th>Channel</th><th>Status</th><th>Languages</th><th>Intents</th><th>Summary</th></tr></thead>
            <tbody>{data.map((c) => (
              <tr key={c.id}>
                <td data-label="Started" className="whitespace-nowrap"><Link className="font-medium text-slate-900 hover:text-brand-500" to={`/calls/${c.id}`}>{fmtDate(c.created_at)}</Link></td>
                <td data-label="Channel" className="whitespace-nowrap text-slate-600"><span className="capitalize">{c.channel.replace('_', ' ')}</span></td>
                <td data-label="Status"><Badge tone={statusTone(c.status)}>{c.status}</Badge></td>
                <td data-label="Languages">{c.languages_used.map((l) => LANGUAGES[l] ?? l).join(', ')}</td>
                <td data-label="Intents"><div className="flex flex-wrap gap-1">{c.intents.map((t) => <code key={t} className="whitespace-nowrap rounded-md bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{t}</code>)}</div></td>
                <td data-label="Summary" className="max-w-md text-slate-600">{c.summary ?? '—'}</td>
              </tr>
            ))}</tbody>
          </table>
        ) : <div className="p-3"><Empty icon={Icons.chat}>{filtered ? 'No calls match these filters.' : 'No conversations yet. Start one from the Voice page.'}</Empty></div>}
        {more && <div className="p-3 text-center"><button className="btn-ghost btn-sm" onClick={() => load(data?.length ?? 0)}>Load more</button></div>}
      </div>
    </div>
  )
}

interface Detail {
  conversation: Conversation
  messages: Message[]
  tool_executions: { tool: string; status: string; arguments: unknown; result: unknown; error: string | null; duration_ms: number; at: string }[]
  escalations: { id: string; reason: string; priority: string; summary: string; status: string; at: string }[]
  call: { duration_seconds: number | null; status: string; end_reason: string | null } | null
}

export function CallDetail() {
  const { id } = useParams()
  const { data, error, reload } = useApi<Detail>(`/conversations/${id}`)
  const toast = useToast()
  const [refreshing, setRefreshing] = useState(false)
  if (!data) return <ErrorNote error={error} />
  const c = data.conversation
  const refresh = async () => {
    setRefreshing(true)
    try {
      const r = await api<{ pending: boolean; messages: number }>(`/conversations/${id}/sarvam-transcript`, { method: 'POST' })
      toast(r.pending ? 'Sarvam hasn’t finished this transcript yet. Try again in a minute.' : `Transcript updated (${r.messages} messages)`)
      if (!r.pending) await reload()
    } catch (e) { toast((e as Error).message, 'error') } finally { setRefreshing(false) }
  }
  return (
    <div>
      <PageHeader eyebrow="Transcript" title="Conversation" subtitle={`${fmtDate(c.created_at)} · ${c.channel.replace('_', ' ')}`}
        actions={<div className="flex gap-2">
          {c.channel === 'sarvam_voice' && <button className="btn-ghost btn-sm" disabled={refreshing} onClick={refresh}>{refreshing ? 'Refreshing…' : 'Refresh transcript'}</button>}
          <Link to="/calls" className="btn-ghost btn-sm">← All calls</Link>
        </div>} />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="card space-y-3">
          {data.messages.map((m) => (
            <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : ''}`}>
              <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${m.role === 'user' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-800'}`}>
                {m.content}
                <div className="mt-1 text-xs opacity-70">{m.language && (LANGUAGES[m.language] ?? m.language)} {m.interrupted && '· interrupted'}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="space-y-4">
          <div className="card text-sm">
            <h2 className="card-title mb-2">Summary</h2>
            <p className="leading-relaxed text-slate-600">{c.summary ?? 'Not available (call in progress or summary failed).'}</p>
            <div className="mt-3 flex flex-wrap gap-2"><Badge tone={statusTone(c.status)}>{c.status}</Badge>
              {data.call?.duration_seconds != null && <Badge>{Math.round(data.call.duration_seconds)}s</Badge>}
              {data.call?.end_reason && <Badge>{data.call.end_reason}</Badge>}</div>
          </div>
          {!!data.escalations.length && (
            <div className="card text-sm"><h2 className="card-title mb-3 text-rose-700">Escalations</h2>
              {data.escalations.map((e) => <div key={e.id} className="mb-2 leading-relaxed"><Badge tone="red">{e.priority}</Badge> <span className="capitalize">{e.reason.replace(/_/g, ' ')}</span> — <span className="text-slate-500">{e.summary}</span></div>)}
            </div>
          )}
          <div className="card text-sm">
            <h2 className="card-title mb-3">Tool executions</h2>
            {data.tool_executions.length ? data.tool_executions.map((t, i) => (
              <details key={i} className="mb-2 rounded-xl border border-slate-200 px-3 py-2.5">
                <summary className="flex cursor-pointer flex-wrap items-center gap-2"><span className="font-mono text-[13px] font-medium text-slate-900">{t.tool}</span> <Badge tone={t.status === 'success' ? 'green' : 'amber'}>{t.status}</Badge> <span className="ml-auto text-xs text-slate-500 tabular-nums">{t.duration_ms}ms</span></summary>
                <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-50 p-2.5 font-mono text-xs leading-relaxed text-slate-600">{JSON.stringify({ arguments: t.arguments, result: t.result, error: t.error }, null, 2)}</pre>
              </details>
            )) : <div className="text-slate-500">None</div>}
          </div>
        </div>
      </div>
    </div>
  )
}
