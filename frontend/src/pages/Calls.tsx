import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useToast } from '../components/Toast'
import { downloadCsv } from '../services/csv'
import { Badge, Empty, ErrorNote, Icons, PageHeader, fmtDate, statusTone } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../hooks/useAuth'
import { api } from '../services/api'
import { LANGUAGES, type Conversation, type Message } from '../types'

const PAGE = 100
const STATUSES = ['all', 'completed', 'escalated', 'abandoned', 'active'] as const

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
          <div className="flex items-center gap-3 px-6 pb-2 pt-5">
            <span className="icon-tile h-8 w-8 rounded-xl bg-gradient-to-br from-[#fb7185] to-[#e11d48] text-[#e11d48]"><span className="text-white">{Icons.alert}</span></span>
            <div>
              <div className="text-[15px] font-semibold text-slate-900">Open escalations</div>
              <div className="text-xs text-slate-500">{escalations.length} waiting for a human</div>
            </div>
            <Link to="/follow-ups?tab=escalations" className="btn-ghost ml-auto">Assign & resolve</Link>
          </div>
          <div className="px-3 pb-3">
            {escalations.map((e) => (
              <Link key={e.id} to={`/calls/${e.conversation_id}`} className="flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition hover:bg-white">
                <Badge tone={e.priority === 'critical' ? 'red' : 'amber'}>{e.priority}</Badge>
                <span className="font-medium capitalize text-slate-900">{e.reason.replace('_', ' ')}</span>
                <span className="min-w-0 flex-1 truncate text-slate-500">{e.summary}</span>
                <span className="whitespace-nowrap text-xs text-slate-400">{fmtDate(e.at)}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {STATUSES.map((st) => (
          <button key={st} onClick={() => setStatus(st)}
            className={`rounded-full px-3 py-1 text-sm capitalize ring-1 ring-inset transition ${status === st ? 'bg-slate-900 text-white ring-slate-900' : 'bg-white text-slate-600 ring-slate-200 hover:ring-slate-300'}`}>{st}</button>
        ))}
        <select aria-label="Channel" className="input w-auto py-1.5" value={channel} onChange={(e) => setChannel(e.target.value)}>
          <option value="">All channels</option><option value="sarvam_voice">Sarvam voice</option><option value="web_text">Web text</option><option value="widget">Website widget</option><option value="phone">Phone</option>
        </select>
        <label className="flex items-center gap-1 text-sm text-slate-500">From <input type="date" aria-label="From date" className="input w-auto py-1.5" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} /></label>
        <label className="flex items-center gap-1 text-sm text-slate-500">To <input type="date" aria-label="To date" className="input w-auto py-1.5" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} /></label>
        <input aria-label="Search calls" className="input ml-auto w-60 py-1.5" placeholder="Search summaries & transcripts…" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn-ghost" onClick={exportCsv} disabled={!data?.length}>Export CSV</button>
      </div>
      <div className="card overflow-x-auto px-3 py-2">
        {!data ? <div className="p-6 text-sm text-slate-400">Loading…</div> : data.length ? (
          <table className="table">
            <thead><tr><th>Started</th><th>Channel</th><th>Status</th><th>Languages</th><th>Intents</th><th>Summary</th></tr></thead>
            <tbody>{data.map((c) => (
              <tr key={c.id} className="hover:bg-slate-50">
                <td className="whitespace-nowrap"><Link className="font-medium text-slate-900 hover:text-brand-500" to={`/calls/${c.id}`}>{fmtDate(c.created_at)}</Link></td>
                <td className="whitespace-nowrap capitalize text-slate-600">{c.channel.replace('_', ' ')}</td>
                <td><Badge tone={statusTone(c.status)}>{c.status}</Badge></td>
                <td>{c.languages_used.map((l) => LANGUAGES[l] ?? l).join(', ')}</td>
                <td><div className="flex flex-wrap gap-1">{c.intents.map((t) => <code key={t} className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">{t}</code>)}</div></td>
                <td className="max-w-md text-xs text-slate-600">{c.summary ?? '—'}</td>
              </tr>
            ))}</tbody>
          </table>
        ) : <div className="p-3"><Empty icon={Icons.chat}>{filtered ? 'No calls match these filters.' : 'No conversations yet. Start one from the Voice page.'}</Empty></div>}
        {more && <div className="p-3 text-center"><button className="btn-ghost" onClick={() => load(data?.length ?? 0)}>Load more</button></div>}
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
          {c.channel === 'sarvam_voice' && <button className="btn-ghost" disabled={refreshing} onClick={refresh}>{refreshing ? 'Refreshing…' : 'Refresh transcript'}</button>}
          <Link to="/calls" className="btn-ghost">← All calls</Link>
        </div>} />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="card space-y-3">
          {data.messages.map((m) => (
            <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : ''}`}>
              <div className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm ${m.role === 'user' ? 'bg-brand-600 text-white' : 'bg-slate-100'}`}>
                {m.content}
                <div className="mt-1 text-[10px] opacity-70">{m.language && (LANGUAGES[m.language] ?? m.language)} {m.interrupted && '· interrupted'}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="space-y-4">
          <div className="card text-sm">
            <div className="mb-2 font-semibold">Summary</div>
            <p className="text-slate-600">{c.summary ?? 'Not available (call in progress or summary failed).'}</p>
            <div className="mt-3 flex flex-wrap gap-2"><Badge tone={statusTone(c.status)}>{c.status}</Badge>
              {data.call?.duration_seconds != null && <Badge>{Math.round(data.call.duration_seconds)}s</Badge>}
              {data.call?.end_reason && <Badge>{data.call.end_reason}</Badge>}</div>
          </div>
          {!!data.escalations.length && (
            <div className="card text-sm"><div className="mb-2 font-semibold text-rose-700">Escalations</div>
              {data.escalations.map((e) => <div key={e.id} className="mb-2"><Badge tone="red">{e.priority}</Badge> {e.reason} — <span className="text-slate-500">{e.summary}</span></div>)}
            </div>
          )}
          <div className="card text-sm">
            <div className="mb-2 font-semibold">Tool executions</div>
            {data.tool_executions.length ? data.tool_executions.map((t, i) => (
              <details key={i} className="mb-2 rounded border border-slate-100 p-2">
                <summary className="cursor-pointer"><span className="font-mono text-xs">{t.tool}</span> <Badge tone={t.status === 'success' ? 'green' : 'amber'}>{t.status}</Badge> <span className="text-xs text-slate-400">{t.duration_ms}ms</span></summary>
                <pre className="mt-2 overflow-x-auto text-[11px] text-slate-600">{JSON.stringify({ arguments: t.arguments, result: t.result, error: t.error }, null, 2)}</pre>
              </details>
            )) : <div className="text-slate-400">None</div>}
          </div>
        </div>
      </div>
    </div>
  )
}
