import { useLayoutEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ErrorNote, Icons, PageHeader, Panel, Skeleton, Stat } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../hooks/useAuth'
import { LANGUAGES } from '../types'

interface Overview {
  total_conversations: number; total_calls: number; answered_calls: number; missed_calls: number
  avg_call_duration_seconds: number; resolved: number; resolution_rate: number | null; escalated: number
  languages: Record<string, number>; channels: Record<string, number>; customer_satisfaction: number | null
  top_tools: { tool: string; count: number }[]; daily: { date: string; count: number }[]
  hours: number[]; timezone: string; by_status: Record<string, number>
  leads: { total: number; by_status: Record<string, number> }; escalations: { total: number; by_status: Record<string, number> }
  sentiment?: { analysed: number; by_label: Record<string, number>; average_score: number | null; needs_human: number }
}

const SENTIMENT_ORDER = ['positive', 'neutral', 'mixed', 'negative'] as const
const SENTIMENT_BAR: Record<string, string> = {
  positive: 'bg-emerald-500', neutral: 'bg-slate-300', mixed: 'bg-amber-400', negative: 'bg-rose-500',
}

/** Share of analysed conversations per sentiment as one stacked bar, with the counts listed underneath. */
function SentimentSummary({ s }: { s: NonNullable<Overview['sentiment']> }) {
  if (!s.analysed) return <div className="py-6 text-center text-sm text-slate-500">No analysed conversations yet. Analysis runs when a conversation ends.</div>
  const score = s.average_score
  return (
    <div className="grid gap-5 sm:grid-cols-[1fr_auto] sm:items-center">
      <div>
        <div className="flex h-3 overflow-hidden rounded-full bg-slate-100" role="img"
          aria-label={SENTIMENT_ORDER.map((k) => `${k} ${s.by_label[k] ?? 0}`).join(', ')}>
          {SENTIMENT_ORDER.map((k) => (s.by_label[k] ?? 0) > 0 && (
            <div key={k} className={`${SENTIMENT_BAR[k]} transition-[width] duration-700`} style={{ width: `${((s.by_label[k] ?? 0) / s.analysed) * 100}%` }} title={`${k}: ${s.by_label[k]}`} />
          ))}
        </div>
        <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-sm">
          {SENTIMENT_ORDER.map((k) => (
            <li key={k}>
              <Link to={`/calls?sentiment=${k}`} className="group flex items-center gap-2 capitalize text-slate-700 hover:text-brand-600">
                <span aria-hidden className={`h-2 w-2 rounded-full ${SENTIMENT_BAR[k]}`} />{k}
                <span className="font-semibold tabular-nums text-slate-900">{s.by_label[k] ?? 0}</span>
                <span className="tabular-nums text-slate-400">{Math.round(((s.by_label[k] ?? 0) / s.analysed) * 100)}%</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
      <div className="flex gap-6 text-sm sm:border-l sm:border-slate-200 sm:pl-6">
        <div><div className="text-slate-500">Average score</div>
          <div className="text-2xl font-semibold tabular-nums text-slate-900" title="−1 very negative … +1 very positive">{score == null ? '—' : `${score > 0 ? '+' : ''}${score.toFixed(2)}`}</div></div>
        <div><div className="text-slate-500">Need a person</div>
          <Link to="/follow-ups?tab=escalations" className="text-2xl font-semibold tabular-nums text-slate-900 hover:text-brand-500">{s.needs_human}</Link></div>
      </div>
    </div>
  )
}

const DAYS = 30

/** Width of the chart's box in CSS px. Charts draw at 1:1, so they keep their height and 11px labels however wide
 *  the page is, instead of scaling up like a picture. */
function useBoxWidth(fallback = 640) {
  const [el, setEl] = useState<HTMLDivElement | null>(null)
  const [width, setWidth] = useState(fallback)
  useLayoutEffect(() => {
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(320, Math.round(e.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [el])
  return [setEl, width] as const
}
const pretty = (k: string) => LANGUAGES[k] ?? k.replace(/_/g, ' ')

/** Horizontal magnitude bars, single hue, value labels in ink (not series colour). */
function Bars({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1])
  const max = Math.max(1, ...entries.map(([, v]) => v))
  if (!entries.length) return <div className="py-6 text-center text-sm text-slate-500">No data yet</div>
  return (
    <ul className="space-y-3.5">
      {entries.map(([k, v]) => (
        <li key={k} title={`${pretty(k)}: ${v}`}>
          <div className="flex items-baseline justify-between text-sm">
            <span className="capitalize text-slate-700">{pretty(k)}</span>
            <span className="font-medium tabular-nums text-slate-900">{v}</span>
          </div>
          <div className="mt-2 h-2 rounded-full bg-slate-100">
            <div className="h-2 rounded-full bg-gradient-to-r from-[#2f8cff] to-brand-500 transition-[width] duration-700" style={{ width: `${(v / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

/** 30-day area chart with crosshair + tooltip. Missing days are zero-filled so the time axis is honest. */
function DailyChart({ daily }: { daily: Overview['daily'] }) {
  const series = useMemo(() => {
    const byDate = new Map(daily.map((d) => [d.date.slice(0, 10), d.count]))
    const out: { date: Date; key: string; count: number }[] = []
    const today = new Date(); today.setHours(0, 0, 0, 0)
    for (let i = DAYS - 1; i >= 0; i--) {
      const d = new Date(today); d.setDate(today.getDate() - i)
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      out.push({ date: d, key, count: byDate.get(key) ?? 0 })
    }
    return out
  }, [daily])
  const [hover, setHover] = useState<number | null>(null)
  const [box, W] = useBoxWidth()
  const H = 220, PL = 28, PB = 22, PT = 10
  const max = Math.max(4, ...series.map((s) => s.count))
  const niceMax = Math.ceil(max / 4) * 4
  const x = (i: number) => PL + (i / (DAYS - 1)) * (W - PL - 8)
  const y = (v: number) => PT + (1 - v / niceMax) * (H - PT - PB)
  const line = series.map((s, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(s.count).toFixed(1)}`).join('')
  const area = `${line}L${x(DAYS - 1)},${y(0)}L${x(0)},${y(0)}Z`
  const total = series.reduce((a, s) => a + s.count, 0)
  const fmt = (d: Date) => d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const h = hover != null ? series[hover] : null

  return (
    <div ref={box} className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={`Conversations per day, last ${DAYS} days, ${total} total`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect()
          const px = ((e.clientX - r.left) / r.width) * W
          setHover(Math.max(0, Math.min(DAYS - 1, Math.round(((px - PL) / (W - PL - 8)) * (DAYS - 1)))))
        }}>
        <defs>
          <linearGradient id="dailyFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0071e3" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#0071e3" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={PL} x2={W - 8} y1={y(niceMax * f)} y2={y(niceMax * f)} stroke="#e5e5ea" strokeWidth="1" />
            <text x={PL - 8} y={y(niceMax * f) + 3.5} textAnchor="end" fontSize="11" fill="#a1a1a6">{niceMax * f}</text>
          </g>
        ))}
        {[0, 10, 20, DAYS - 1].map((i) => (
          <text key={i} x={x(i)} y={H - 4} textAnchor={i === 0 ? 'start' : i === DAYS - 1 ? 'end' : 'middle'} fontSize="11" fill="#a1a1a6">{fmt(series[i].date)}</text>
        ))}
        <path d={area} fill="url(#dailyFill)" />
        <path d={line} fill="none" stroke="#0071e3" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {h && hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={PT} y2={y(0)} stroke="#1d1d1f" strokeOpacity="0.15" />
            <circle cx={x(hover)} cy={y(h.count)} r="5" fill="#0071e3" stroke="#fff" strokeWidth="2" />
          </g>
        )}
      </svg>
      {h && hover != null && (
        <div className="pointer-events-none absolute top-0 -translate-x-1/2 rounded-xl bg-slate-900/90 px-3 py-1.5 text-xs text-white shadow-lg backdrop-blur"
          style={{ left: `${(x(hover) / W) * 100}%` }}>
          <div className="font-medium">{fmt(h.date)}</div>
          <div className="text-white/70">{h.count} conversation{h.count === 1 ? '' : 's'}</div>
        </div>
      )}
    </div>
  )
}

const hourLabel = (h: number) => `${h % 12 || 12} ${h < 12 ? 'AM' : 'PM'}`

/** Calls by hour of day (business timezone): 24 columns, single hue, peak labelled, per-column tooltip. */
function HourChart({ hours, timezone }: { hours: number[]; timezone: string }) {
  const [hover, setHover] = useState<number | null>(null)
  const [box, W] = useBoxWidth()
  const H = 200, PL = 28, PB = 22, PT = 18
  const max = Math.max(4, ...hours)
  const niceMax = Math.ceil(max / 4) * 4
  const slot = (W - PL - 8) / 24
  const bw = Math.min(24, slot - 2) // <=24px thick, 2px surface gap between neighbours
  const x = (i: number) => PL + i * slot + (slot - bw) / 2
  const y = (v: number) => PT + (1 - v / niceMax) * (H - PT - PB)
  const base = y(0)
  const peak = hours.reduce((best, v, i) => (v > hours[best] ? i : best), 0)
  const total = hours.reduce((a, v) => a + v, 0)
  // Rounded 4px data-end, square at the baseline.
  const col = (i: number, v: number) => {
    const top = y(v), r = Math.min(4, (base - top) / 2, bw / 2), l = x(i), rt = l + bw
    return `M${l},${base}V${top + r}Q${l},${top} ${l + r},${top}H${rt - r}Q${rt},${top} ${rt},${top + r}V${base}Z`
  }
  if (!total) return <div className="py-6 text-center text-sm text-slate-500">No calls yet</div>
  return (
    <div ref={box} className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img"
        aria-label={`Calls by hour of day in ${timezone}. Busiest: ${hourLabel(peak)} with ${hours[peak]}.`} onMouseLeave={() => setHover(null)}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={PL} x2={W - 8} y1={y(niceMax * f)} y2={y(niceMax * f)} stroke="#e5e5ea" strokeWidth="1" />
            <text x={PL - 8} y={y(niceMax * f) + 3.5} textAnchor="end" fontSize="11" fill="#a1a1a6">{niceMax * f}</text>
          </g>
        ))}
        {hours.map((v, i) => (
          <g key={i} onMouseEnter={() => setHover(i)}>
            {/* Hit target spans the whole slot, taller than the mark. */}
            <rect x={PL + i * slot} y={PT} width={slot} height={base - PT} fill="transparent" />
            {v > 0 && <path d={col(i, v)} fill="#0071e3" fillOpacity={hover == null || hover === i ? 1 : 0.45} />}
          </g>
        ))}
        {hours[peak] > 0 && <text x={x(peak) + bw / 2} y={y(hours[peak]) - 5} textAnchor="middle" fontSize="11" fontWeight="600" fill="#1d1d1f">{hours[peak]}</text>}
        {[0, 6, 12, 18].map((i) => (
          <text key={i} x={x(i)} y={H - 4} fontSize="11" fill="#a1a1a6">{hourLabel(i)}</text>
        ))}
      </svg>
      {hover != null && (
        <div className="pointer-events-none absolute top-0 -translate-x-1/2 rounded-xl bg-slate-900/90 px-3 py-1.5 text-xs text-white shadow-lg backdrop-blur"
          style={{ left: `${((x(hover) + bw / 2) / W) * 100}%` }}>
          <div className="font-medium">{hourLabel(hover)} – {hourLabel((hover + 1) % 24)}</div>
          <div className="text-white/70">{hours[hover]} conversation{hours[hover] === 1 ? '' : 's'}</div>
        </div>
      )}
      <table className="sr-only"><caption>Conversations by hour ({timezone})</caption>
        <tbody>{hours.map((v, i) => <tr key={i}><th>{hourLabel(i)}</th><td>{v}</td></tr>)}</tbody></table>
    </div>
  )
}

const LEAD_ORDER = ['new', 'qualified', 'contacted', 'won', 'lost']
const LEAD_DOT: Record<string, string> = {
  new: 'bg-brand-500', qualified: 'bg-violet-accent', contacted: 'bg-amber-500', won: 'bg-emerald-500', lost: 'bg-slate-400',
}

/** Lead pipeline as counts (not a chart: five numbers read faster as numbers). One row per stage so the
 *  labels never truncate, however narrow the panel. */
function FollowUpSummary({ leads, escalations }: { leads: Overview['leads']; escalations: Overview['escalations'] }) {
  const won = leads.by_status.won ?? 0
  const closed = won + (leads.by_status.lost ?? 0)
  const open = (escalations.by_status.open ?? 0) + (escalations.by_status.assigned ?? 0)
  return (
    <div>
      <ul className="divide-y divide-slate-100">
        {LEAD_ORDER.map((st) => (
          <li key={st}>
            <Link to="/follow-ups" className="group flex items-center justify-between py-2 text-sm">
              <span className="flex items-center gap-2.5 capitalize text-slate-700 group-hover:text-brand-600">
                <span aria-hidden className={`h-2 w-2 rounded-full ${LEAD_DOT[st]}`} />{st}
              </span>
              <span className="font-semibold tabular-nums text-slate-900">{leads.by_status[st] ?? 0}</span>
            </Link>
          </li>
        ))}
      </ul>
      <div className="mt-3 space-y-2 border-t border-slate-200 pt-3 text-sm text-slate-600">
        <div className="flex justify-between"><span>Win rate (of closed leads)</span>
          <span className="font-medium tabular-nums text-slate-900">{closed ? `${Math.round((won / closed) * 100)}%` : '—'}</span></div>
        <div className="flex justify-between"><span>Escalations waiting</span>
          <Link to="/follow-ups?tab=escalations" className="font-medium tabular-nums text-slate-900 hover:text-brand-500">{open}</Link></div>
      </div>
    </div>
  )
}

function greeting() {
  const hr = new Date().getHours()
  return hr < 12 ? 'Good morning' : hr < 17 ? 'Good afternoon' : 'Good evening'
}

export default function Dashboard() {
  const { data, error } = useApi<Overview>(`/analytics/overview?days=${DAYS}`)
  const { user, tenants, tenantId } = useAuth()
  const business = user?.role === 'platform_admin' ? tenants.find((t) => t.id === tenantId)?.name : user?.tenant_name
  const rate = data?.resolution_rate == null ? null : Math.round(data.resolution_rate * 100)

  return (
    <div>
      <PageHeader eyebrow={`Overview · last ${DAYS} days`}
        title={<>{greeting()},<br className="sm:hidden" /> <span className="text-gradient">{business ?? 'Your business'}</span></>}
        subtitle="How your AI agents handled callers this month."
        actions={<Link to="/agents" className="btn">{Icons.phone} Test your agent</Link>} />
      <ErrorNote error={error} />

      {!data && !error && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 2xl:grid-cols-6">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-32 rounded-3xl" />)}</div>
      )}

      {data && (
        <>
          <div className="stagger grid grid-cols-2 gap-4 lg:grid-cols-3 2xl:grid-cols-6">
            <Stat label="Total calls" value={data.total_calls} hint={`${data.total_conversations} conversations including text`} icon={Icons.phone} tone="blue" />
            <Stat label="Answered / missed" value={<>{data.answered_calls}<span className="text-slate-300"> / </span>{data.missed_calls}</>} icon={Icons.check} tone="green" />
            <Stat label="Avg call duration" value={`${Math.round(data.avg_call_duration_seconds)}s`} icon={Icons.clock} tone="violet" />
            <Stat label="Resolution rate" value={rate == null ? '—' : `${rate}%`} hint={`${data.resolved} resolved`} icon={Icons.target} tone="green" />
            <Stat label="Escalated" value={data.escalated} hint="Handed to a human" icon={Icons.alert} tone={data.escalated ? 'rose' : 'slate'} />
            <Stat label="Customer satisfaction" value={data.customer_satisfaction ?? '—'} hint="Post-call rating (Phase 5)" icon={Icons.star} tone="amber" />
          </div>

          <div className="stagger mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Panel className="lg:col-span-2" title="Conversations per day" subtitle={`${data.daily.reduce((a, d) => a + d.count, 0)} in the last ${DAYS} days`}>
              <DailyChart daily={data.daily} />
            </Panel>
            <Panel title="Languages" subtitle="Detected per conversation"><Bars data={data.languages} /></Panel>
            {/* Rows fill the 3-column grid exactly: day chart + languages, three breakdowns, hours chart + leads. */}
            <Panel title="Channels"><Bars data={data.channels} /></Panel>
            <Panel title="Most used tools" subtitle="What callers asked the agent to do">
              <Bars data={Object.fromEntries(data.top_tools.map((t) => [t.tool, t.count]))} />
            </Panel>
            <Panel title="Outcomes" subtitle="How conversations ended"><Bars data={data.by_status} /></Panel>
            {/* Guarded: an older backend (e.g. a partial manual upload) doesn't send these fields. */}
            {data.hours && (
              <Panel className="lg:col-span-2" title="Busiest hours" subtitle={`When conversations start (${data.timezone} time)`}>
                <HourChart hours={data.hours} timezone={data.timezone} />
              </Panel>
            )}
            {data.leads && data.escalations && (
              <Panel title="Leads & follow-ups" subtitle={`${data.leads.total} leads captured`}>
                <FollowUpSummary leads={data.leads} escalations={data.escalations} />
              </Panel>
            )}
            {data.sentiment && (
              <Panel className="lg:col-span-3" title="Caller sentiment" subtitle={`From the AI analysis of ${data.sentiment.analysed} ended conversation${data.sentiment.analysed === 1 ? '' : 's'}`}>
                <SentimentSummary s={data.sentiment} />
              </Panel>
            )}
          </div>
        </>
      )}
    </div>
  )
}
