import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { DateRangePicker } from '../components/DatePicker'
import { Select } from '../components/Select'
import { useToast } from '../components/Toast'
import { downloadCsv } from '../services/csv'
import { todayKey } from '../services/dates'
import { Badge, Empty, ErrorNote, Icons, PageHeader, fmtDate, statusTone } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../hooks/useAuth'
import { api } from '../services/api'
import { LANGUAGES, SENTIMENT_TONE, type Analysis, type Conversation, type Message } from '../types'

const PAGE = 100
const STATUSES = ['all', 'completed', 'escalated', 'abandoned', 'active'] as const
const CHANNELS = [
  { value: '', label: 'All channels' }, { value: 'sarvam_voice', label: 'Sarvam voice' }, { value: 'web_text', label: 'Web text' },
  { value: 'widget', label: 'Website widget' }, { value: 'phone', label: 'Phone' },
]
const SENTIMENTS = [
  { value: '', label: 'Any sentiment' }, { value: 'positive', label: 'Positive' }, { value: 'neutral', label: 'Neutral' },
  { value: 'mixed', label: 'Mixed' }, { value: 'negative', label: 'Negative' },
]

export function Calls() {
  const { tenantId } = useAuth()
  const toast = useToast()
  const [status, setStatus] = useState<string>('all')
  const [channel, setChannel] = useState('')
  const [search] = useSearchParams() // the dashboard's sentiment panel links here with ?sentiment=
  const [sentiment, setSentiment] = useState(() => SENTIMENTS.some((o) => o.value && o.value === search.get('sentiment')) ? search.get('sentiment')! : '')
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
    if (sentiment) u.set('sentiment', sentiment)
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
  useEffect(() => { setData(null); load(0) }, [status, channel, sentiment, query, from, to, tenantId])

  const exportCsv = () => {
    if (!data?.length) return
    downloadCsv('calls', ['Started', 'Ended', 'Channel', 'Status', 'Sentiment', 'Outcome', 'Languages', 'Intents', 'Summary'],
      data.map((c) => [c.created_at, c.ended_at, c.channel, c.status, c.sentiment ?? '', c.outcome ?? '', c.languages_used.map((l) => LANGUAGES[l] ?? l).join(' / '), c.intents.join(' / '), c.summary]))
    toast(`Exported ${data.length} calls`)
  }
  const filtered = status !== 'all' || channel || sentiment || query || from || to
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
        <Select label="Sentiment" size="sm" className="w-auto min-w-36" value={sentiment} onChange={setSentiment} options={SENTIMENTS} />
        <DateRangePicker size="sm" label="Call dates" value={{ from, to }} max={todayKey()}
          onChange={(r) => { setFrom(r.from); setTo(r.to) }} />
        <input aria-label="Search calls" type="search" className="input input-sm min-w-36 flex-1" placeholder="Search transcripts…" title="Searches call summaries and transcripts" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn-ghost btn-sm" onClick={exportCsv} disabled={!data?.length}>Export CSV</button>
      </div>
      <div className="card card-table">
        {!data ? <div className="p-6 text-sm text-slate-500">Loading…</div> : data.length ? (
          <table className="table table-stack">
            <thead><tr><th>Started</th><th>Channel</th><th>Status</th><th>Sentiment</th><th>Languages</th><th>Intents</th><th>Summary</th></tr></thead>
            <tbody>{data.map((c) => (
              <tr key={c.id}>
                <td data-label="Started" className="whitespace-nowrap"><Link className="font-medium text-slate-900 hover:text-brand-500" to={`/calls/${c.id}`}>{fmtDate(c.created_at)}</Link></td>
                <td data-label="Channel" className="whitespace-nowrap text-slate-600"><span className="capitalize">{c.channel.replace('_', ' ')}</span></td>
                <td data-label="Status"><Badge tone={statusTone(c.status)}>{c.status}</Badge></td>
                <td data-label="Sentiment">{c.sentiment
                  ? <span className="inline-flex items-center gap-1.5"><Badge tone={SENTIMENT_TONE[c.sentiment]}>{c.sentiment}</Badge>
                    {c.needs_human && <span title="A person should follow up" className="text-rose-600">{Icons.alert}</span>}</span>
                  : <span className="text-slate-400">—</span>}</td>
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
  analysis: Analysis | null
}

const signed = (score: number) => `${score > 0 ? '+' : ''}${score.toFixed(2)}`
const words = (s: string) => s.replace(/_/g, ' ')
const label = 'mb-1 text-xs font-medium uppercase tracking-wide text-slate-500'

/** The post-call analyst's findings, or why there are none, with a button to run it again. */
function AnalysisCard({ a, ended, onRerun, running }: { a: Analysis | null; ended: boolean; onRerun: () => void; running: boolean }) {
  const rerun = ended && <button className="btn-ghost btn-sm" disabled={running} onClick={onRerun}>{running ? 'Analysing…' : a ? 'Re-run' : 'Analyse'}</button>
  const header = <div className="flex items-center justify-between gap-2"><h2 className="card-title">AI analysis</h2>{rerun}</div>
  if (!a || a.status !== 'done') {
    const why = !a ? (ended ? 'This conversation hasn’t been analysed yet.' : 'Analysis runs when the conversation ends.')
      : a.status === 'skipped' ? 'Nothing to analyse: the caller didn’t say anything.'
        : a.status === 'not_configured' ? 'Analysis is off: set SARVAM_API_KEY on the server.'
          : `Analysis failed: ${a.error ?? 'unknown error'}`
    return <div className="card space-y-2 text-sm">{header}<p className="leading-relaxed text-slate-500">{why}</p></div>
  }
  return (
    <div className="card space-y-3 text-sm">
      {header}
      <div className="flex flex-wrap items-center gap-2">
        {a.sentiment && <Badge tone={SENTIMENT_TONE[a.sentiment]}>{a.sentiment}</Badge>}
        {a.sentiment_score != null && <span className="tabular-nums text-slate-600" title="−1 very negative … +1 very positive">{signed(a.sentiment_score)}</span>}
        {a.sentiment_trend && <span className="text-slate-500">· {a.sentiment_trend}</span>}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
        {a.outcome && <><dt className="text-slate-500">Outcome</dt><dd className="capitalize text-slate-900">{words(a.outcome)}</dd></>}
        <dt className="text-slate-500">Resolved</dt><dd className="text-slate-900">{a.resolved ? 'Yes' : 'No'}</dd>
        {!!a.emotions.length && <><dt className="text-slate-500">Emotions</dt><dd className="text-slate-900">{a.emotions.join(', ')}</dd></>}
        {!!a.topics.length && <><dt className="text-slate-500">Topics</dt><dd className="text-slate-900">{a.topics.join(', ')}</dd></>}
      </dl>
      {!!a.key_quotes.length && (
        <div><div className={label}>Caller said</div>
          {a.key_quotes.map((q) => <blockquote key={q} className="mb-1 border-l-2 border-slate-200 pl-2.5 italic text-slate-700">“{q}”</blockquote>)}
        </div>
      )}
      {!!a.follow_ups.length && (
        <div><div className={`${label} flex items-center gap-2`}>Follow-ups
          {a.escalation_id && <Link to="/follow-ups?tab=escalations" className="normal-case tracking-normal text-brand-600 hover:underline">in queue →</Link>}</div>
          <ul className="space-y-1.5">{a.follow_ups.map((f, i) => (
            <li key={i} className="flex items-start gap-2"><Badge tone={f.priority === 'high' ? 'red' : f.priority === 'low' ? 'gray' : 'amber'}>{f.priority}</Badge><span className="text-slate-700">{f.action}</span></li>
          ))}</ul>
        </div>
      )}
      {!!a.agent_issues.length && (
        <div><div className={label}>Where the agent fell short</div>
          <ul className="list-disc space-y-0.5 pl-5 text-slate-700">{a.agent_issues.map((x) => <li key={x}>{x}</li>)}</ul>
        </div>
      )}
      {!!a.checks.length && (
        <details className="text-xs text-slate-500"><summary className="cursor-pointer">Fact checks corrected {a.checks.length} finding{a.checks.length > 1 ? 's' : ''}</summary>
          <ul className="mt-1 list-disc pl-5">{a.checks.map((x) => <li key={x}>{x}</li>)}</ul></details>
      )}
    </div>
  )
}

export function CallDetail() {
  const { id } = useParams()
  const { data, error, reload } = useApi<Detail>(`/conversations/${id}`)
  const toast = useToast()
  const [refreshing, setRefreshing] = useState(false)
  const [analysing, setAnalysing] = useState(false)
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
  const rerun = async () => {
    setAnalysing(true)
    try {
      const a = await api<Analysis>(`/conversations/${id}/analysis`, { method: 'POST' })
      if (a.status === 'done') toast('Analysis updated')
      else toast(a.error ?? 'The analysis didn’t finish', 'error')
      await reload()
    } catch (e) { toast((e as Error).message, 'error') } finally { setAnalysing(false) }
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
          <AnalysisCard a={data.analysis} ended={c.status !== 'active'} onRerun={rerun} running={analysing} />
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
