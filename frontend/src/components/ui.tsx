import type { ReactNode } from 'react'

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: ReactNode; subtitle?: string; actions?: ReactNode; eyebrow?: string }) {
  return (
    <div className="animate-rise mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow mb-2.5">{eyebrow}</p>}
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900 md:text-4xl">{title}</h1>
        {subtitle && <p className="mt-2.5 max-w-2xl text-base leading-relaxed text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

const statTones = {
  blue: 'from-[#2f8cff] to-brand-500 text-brand-500',
  violet: 'from-[#a77bff] to-[#7c4dff] text-[#7c4dff]',
  green: 'from-[#34d399] to-[#10b981] text-[#10b981]',
  amber: 'from-[#fbbf24] to-[#f59e0b] text-[#f59e0b]',
  rose: 'from-[#fb7185] to-[#e11d48] text-[#e11d48]',
  slate: 'from-[#8e8e93] to-[#636366] text-[#636366]',
} as const

export function Stat({ label, value, hint, icon, tone = 'blue' }: {
  label: string; value: ReactNode; hint?: string; icon?: ReactNode; tone?: keyof typeof statTones
}) {
  return (
    <div className="card card-hover p-4 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="pt-1 text-sm font-medium text-slate-600 sm:text-base">{label}</div>
        {icon && <div className={`icon-tile h-8 w-8 rounded-xl sm:h-10 sm:w-10 sm:rounded-2xl bg-gradient-to-br ${statTones[tone]}`}><span className="text-white">{icon}</span></div>}
      </div>
      <div className="mt-3 text-[1.75rem] font-semibold sm:mt-4 sm:text-[2rem] leading-none tracking-tight text-slate-900 tabular-nums">{value}</div>
      {hint && <div className="mt-2 text-xs text-slate-500 sm:mt-2.5 sm:text-sm">{hint}</div>}
    </div>
  )
}

const tones: Record<string, string> = {
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-200/70 [--dot:#10b981]',
  red: 'bg-rose-50 text-rose-700 ring-rose-200/70 [--dot:#e11d48]',
  amber: 'bg-amber-50 text-amber-800 ring-amber-200/70 [--dot:#f59e0b]',
  blue: 'bg-brand-50 text-brand-700 ring-brand-100 [--dot:#0071e3]',
  gray: 'bg-slate-100 text-slate-600 ring-slate-200 [--dot:#a1a1a6]',
}

export function Badge({ children, tone = 'gray' }: { children: ReactNode; tone?: keyof typeof tones }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ring-1 ring-inset ${tones[tone]}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-[var(--dot)]" aria-hidden />
      {children}
    </span>
  )
}

export function statusTone(s: string): keyof typeof tones {
  return ({
    completed: 'green', indexed: 'green', escalated: 'red', failed: 'red', active: 'blue', abandoned: 'amber', pending: 'amber',
    booked: 'blue', cancelled: 'red', no_show: 'amber',
  } as const)[s as 'completed'] ?? 'gray'
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null
  return (
    <div role="alert" className="mb-6 flex items-start gap-3 rounded-2xl bg-rose-50 px-5 py-3.5 text-sm text-rose-800 ring-1 ring-inset ring-rose-200/70">
      <svg viewBox="0 0 24 24" className="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5M12 16h.01" /></svg>
      <span>{error}</span>
    </div>
  )
}

export function SuccessNote({ children }: { children: ReactNode }) {
  if (!children) return null
  return (
    <div role="status" className="mb-6 flex items-start gap-3 rounded-2xl bg-emerald-50 px-5 py-3.5 text-sm text-emerald-800 ring-1 ring-inset ring-emerald-200/70">
      <svg viewBox="0 0 24 24" className="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M20 6 9 17l-5-5" /></svg>
      <span>{children}</span>
    </div>
  )
}

export function Empty({ children, icon }: { children: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-slate-300 bg-white/60 p-12 text-center text-sm text-slate-500">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
        {icon ?? <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M4 7h16M4 12h16M4 17h10" /></svg>}
      </div>
      <div className="max-w-sm">{children}</div>
    </div>
  )
}

export function Skeleton({ className = 'h-24' }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden />
}

/** A titled card section. */
export function Panel({ title, subtitle, actions, children, className = '' }: {
  title?: ReactNode; subtitle?: string; actions?: ReactNode; children: ReactNode; className?: string
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {subtitle && <p className="card-desc">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  )
}

/** Small line icons (24px grid, stroke = currentColor). */
const I = ({ d, children }: { d?: string; children?: ReactNode }) => (
  <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    {d ? <path d={d} /> : children}
  </svg>
)
export const Icons = {
  phone: <I d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" />,
  check: <I d="M20 6 9 17l-5-5" />,
  clock: <I><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></I>,
  target: <I><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1" /></I>,
  alert: <I d="M12 3 2 21h20L12 3zM12 10v4M12 17.5h.01" />,
  star: <I d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z" />,
  chat: <I d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12z" />,
}

export function fmtDate(s: string | null | undefined) {
  // e.g. "13 Nov 2026, 7:37 pm": same day-month order as the date picker, no seconds.
  return s ? new Date(s.endsWith('Z') || s.includes('+') ? s : `${s}Z`).toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit',
  }) : '—'
}
