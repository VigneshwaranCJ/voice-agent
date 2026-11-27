import { useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from 'react'
import { useDismiss, type DismissReason } from '../hooks/useDismiss'
import { addDays, addMonths, clampKey, dayKey, fmt, formatDay, formatRange, parseDay, todayKey, type DateRange } from '../services/dates'

// 1 Jan 2023 was a Sunday; weeks start on Sunday.
const WEEKDAYS = Array.from({ length: 7 }, (_, i) => ({
  narrow: new Date(2023, 0, 1 + i).toLocaleDateString(undefined, { weekday: 'narrow' }),
  long: new Date(2023, 0, 1 + i).toLocaleDateString(undefined, { weekday: 'long' }),
}))

const Chevron = ({ dir }: { dir: 'left' | 'right' }) => (
  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d={dir === 'left' ? 'm15 6-6 6 6 6' : 'm9 6 6 6-6 6'} />
  </svg>
)
const CalendarIcon = () => (
  <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0 text-slate-500" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" /><path d="M3.5 10h17M8 3v4M16 3v4" />
  </svg>
)

/** One month of days. `start`/`end` mark the selection: the same day for a single date, or the two ends of a range. */
function Calendar({ month, onMonth, start, end, onPick, onHover, min, max }: {
  month: Date; onMonth: (d: Date) => void
  start?: string; end?: string
  onPick: (k: string) => void; onHover?: (k: string | null) => void
  min?: string; max?: string
}) {
  const grid = useRef<HTMLDivElement>(null)
  const viaKeyboard = useRef(false)
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const monthPrefix = dayKey(first).slice(0, 7)
  const inMonth = (k: string) => k.startsWith(monthPrefix)
  const today = todayKey()
  const [focus, setFocus] = useState(() => clampKey(
    start && inMonth(start) ? start : inMonth(today) ? today : dayKey(first), min, max))
  const tabKey = inMonth(focus) ? focus : clampKey(dayKey(first), min, max)

  const gridStart = addDays(first, -first.getDay())
  const days = Array.from({ length: 42 }, (_, i) => dayKey(addDays(gridStart, i)))
  const disabled = (k: string) => (!!min && k < min) || (!!max && k > max)
  const a = start || end, b = end || start
  const lo = a && b ? (a < b ? a : b) : undefined
  const hi = a && b ? (a < b ? b : a) : undefined
  const ranged = !!lo && !!hi && lo !== hi

  // Opening the picker puts focus on the selected day (or today), so the keyboard works straight away.
  useEffect(() => { grid.current?.querySelector<HTMLButtonElement>('button[tabindex="0"]')?.focus() }, [])
  useEffect(() => {
    if (!viaKeyboard.current) return
    viaKeyboard.current = false
    grid.current?.querySelector<HTMLButtonElement>(`button[data-day="${focus}"]`)?.focus()
  }, [focus, monthPrefix])

  const onKey = (e: KeyboardEvent) => {
    const cur = parseDay(tabKey)
    const moves: Record<string, () => Date> = {
      ArrowLeft: () => addDays(cur, -1), ArrowRight: () => addDays(cur, 1),
      ArrowUp: () => addDays(cur, -7), ArrowDown: () => addDays(cur, 7),
      Home: () => addDays(cur, -cur.getDay()), End: () => addDays(cur, 6 - cur.getDay()),
      PageUp: () => addMonths(cur, e.shiftKey ? -12 : -1), PageDown: () => addMonths(cur, e.shiftKey ? 12 : 1),
    }
    if (!moves[e.key]) return
    e.preventDefault()
    const k = clampKey(dayKey(moves[e.key]()), min, max)
    viaKeyboard.current = true
    setFocus(k)
    if (!inMonth(k)) onMonth(parseDay(k))
  }

  const prevDisabled = !!min && dayKey(addDays(first, -1)) < min
  const nextDisabled = !!max && dayKey(addMonths(first, 1)) > max
  const navBtn = 'flex h-8 w-8 items-center justify-center rounded-full text-slate-600 transition hover:bg-slate-900/[0.06] hover:text-slate-900 disabled:pointer-events-none disabled:opacity-30'
  const title = first.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })

  return (
    <div className="w-[17.5rem]">
      <div className="mb-1 flex items-center justify-between">
        <button type="button" className={navBtn} disabled={prevDisabled} aria-label="Previous month" onClick={() => onMonth(addMonths(first, -1))}><Chevron dir="left" /></button>
        <div className="text-sm font-semibold text-slate-900" aria-live="polite">{title}</div>
        <button type="button" className={navBtn} disabled={nextDisabled} aria-label="Next month" onClick={() => onMonth(addMonths(first, 1))}><Chevron dir="right" /></button>
      </div>
      <div ref={grid} role="grid" aria-label={title} onKeyDown={onKey} onMouseLeave={() => onHover?.(null)}>
        <div role="row" className="grid grid-cols-7">
          {WEEKDAYS.map((w) => (
            <div key={w.long} role="columnheader" aria-label={w.long} className="flex h-8 items-center justify-center text-xs font-medium text-slate-500">{w.narrow}</div>
          ))}
        </div>
        {[0, 1, 2, 3, 4, 5].map((row) => (
          <div key={row} role="row" className="grid grid-cols-7">
            {days.slice(row * 7, row * 7 + 7).map((k, col) => {
              const endpoint = k === lo || k === hi
              const inside = ranged && k > lo! && k < hi!
              // The range band runs behind the day circles; the ends get half a band towards the inside.
              const band = inside ? `bg-brand-50 ${col === 0 ? 'rounded-l-full' : ''} ${col === 6 ? 'rounded-r-full' : ''}`
                : ranged && k === lo ? 'bg-gradient-to-r from-transparent from-50% to-brand-50 to-50%'
                  : ranged && k === hi ? 'bg-gradient-to-l from-transparent from-50% to-brand-50 to-50%' : ''
              const off = disabled(k)
              const isToday = k === today
              const tone = endpoint ? 'bg-brand-500 font-semibold text-white'
                : off ? 'cursor-not-allowed text-slate-300'
                  : `hover:bg-slate-900/[0.07] ${isToday ? 'font-semibold text-brand-600' : inMonth(k) ? 'text-slate-700' : 'text-slate-400'}`
              return (
                <div key={k} role="gridcell" aria-selected={endpoint || inside} className={`flex h-9 items-center justify-center ${band}`}>
                  <button type="button" data-day={k} tabIndex={k === tabKey ? 0 : -1} disabled={off}
                    aria-label={fmt(k, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                    aria-current={isToday ? 'date' : undefined}
                    onClick={() => { setFocus(k); if (!inMonth(k)) onMonth(parseDay(k)); onPick(k) }}
                    onMouseEnter={() => onHover?.(k)}
                    className={`relative flex h-9 w-9 items-center justify-center rounded-full text-sm tabular-nums transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1 ${tone}`}>
                    {parseDay(k).getDate()}
                    {isToday && !endpoint && <span aria-hidden className="absolute bottom-1 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-brand-500" />}
                  </button>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

/** Drops below its trigger and nudges sideways so it never runs off the screen. */
function Popover({ label, children }: { label: string; children: ReactNode }) {
  const el = useRef<HTMLDivElement>(null)
  const [shift, setShift] = useState(0)
  useLayoutEffect(() => {
    const box = el.current, anchor = box?.parentElement
    if (!box || !anchor) return
    // Screen width from documentElement.clientWidth, not window.innerWidth: Android Chrome widens innerWidth to take in
    // whatever overflows the page, including this popover before it's moved, so the overflow would hide itself.
    const screen = document.documentElement.clientWidth
    const gutter = 12
    const left = anchor.getBoundingClientRect().left
    const width = box.offsetWidth // layout width, unaffected by the opening animation's scale
    let s = Math.min(0, screen - gutter - (left + width))
    if (left + s < gutter) s = gutter - left
    setShift(s)
  }, [])
  return (
    <div ref={el} role="dialog" aria-label={label} style={{ marginLeft: shift }}
      className="animate-pop absolute left-0 top-full z-40 mt-2 rounded-2xl bg-white p-3 shadow-[var(--shadow-float)] ring-1 ring-black/5">
      {children}
    </div>
  )
}

/** The field that opens a picker: looks like the other inputs, with a clear button once a value is set. */
function Trigger({ buttonRef, id, open, onOpen, onClear, text, placeholder, label, size }: {
  buttonRef: Ref<HTMLButtonElement>; id?: string; open: boolean; onOpen: () => void; onClear?: () => void
  text: string | null; placeholder: string; label: string; size: 'sm' | 'md'
}) {
  return (
    <>
      <button ref={buttonRef} id={id} type="button" aria-haspopup="dialog" aria-expanded={open} aria-label={`${label}: ${text ?? placeholder}`}
        onClick={onOpen}
        className={`input ${size === 'sm' ? 'input-sm' : ''} inline-flex min-w-[11.5rem] cursor-pointer items-center gap-2 text-left ${onClear ? 'pr-9' : ''}`}>
        <CalendarIcon />
        <span className={`truncate ${text ? 'text-slate-800' : 'text-slate-500'}`}>{text ?? placeholder}</span>
      </button>
      {onClear && (
        <button type="button" aria-label={`Clear ${label.toLowerCase()}`} onClick={onClear}
          className="absolute right-1.5 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-900/[0.07] hover:text-slate-800">
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6 6 18" /></svg>
        </button>
      )}
    </>
  )
}

/** A single date. `value` is 'YYYY-MM-DD' or '' for none. */
export function DatePicker({ value, onChange, min, max, id, label = 'Date', placeholder = 'Pick a date', size = 'md' }: {
  value: string; onChange: (v: string) => void; min?: string; max?: string; id?: string
  label?: string; placeholder?: string; size?: 'sm' | 'md'
}) {
  const [open, setOpen] = useState(false)
  const [month, setMonth] = useState(() => new Date())
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const close = useCallback((reason: DismissReason) => { setOpen(false); if (reason === 'escape') trigger.current?.focus() }, [])
  useDismiss(open, root, close)
  const pick = (k: string) => { onChange(k); setOpen(false); trigger.current?.focus() }
  const today = todayKey()
  const todayAllowed = clampKey(today, min, max) === today

  return (
    <div ref={root} className="relative inline-block">
      <Trigger buttonRef={trigger} id={id} open={open} label={label} placeholder={placeholder} size={size}
        text={value ? formatDay(value) : null} onClear={value ? () => onChange('') : undefined}
        onOpen={() => { if (open) return setOpen(false); setMonth(value ? parseDay(value) : new Date()); setOpen(true) }} />
      {open && (
        <Popover label={label}>
          <Calendar month={month} onMonth={setMonth} start={value || undefined} end={value || undefined} onPick={pick} min={min} max={max} />
          <div className="mt-3 flex items-center justify-between gap-2 border-t border-slate-100 pt-3">
            <button type="button" className="btn-ghost btn-xs" disabled={!todayAllowed} onClick={() => pick(today)}>Today</button>
            <button type="button" className="btn-ghost btn-xs" disabled={!value} onClick={() => pick('')}>Clear</button>
          </div>
        </Popover>
      )}
    </div>
  )
}

function rangePresets(): { label: string; range: DateRange }[] {
  const t = new Date(), k = dayKey(t)
  const monthStart = new Date(t.getFullYear(), t.getMonth(), 1)
  const yesterday = dayKey(addDays(t, -1))
  return [
    { label: 'Today', range: { from: k, to: k } },
    { label: 'Yesterday', range: { from: yesterday, to: yesterday } },
    { label: 'Last 7 days', range: { from: dayKey(addDays(t, -6)), to: k } },
    { label: 'Last 30 days', range: { from: dayKey(addDays(t, -29)), to: k } },
    { label: 'This month', range: { from: dayKey(monthStart), to: k } },
    { label: 'Last month', range: { from: dayKey(addMonths(monthStart, -1)), to: dayKey(addDays(monthStart, -1)) } },
    { label: 'All time', range: { from: '', to: '' } },
  ]
}

/** A from–to range with quick presets. Click the first day, then the last; the range applies on the second click. */
export function DateRangePicker({ value, onChange, min, max, label = 'Dates', placeholder = 'All dates', size = 'md' }: {
  value: DateRange; onChange: (r: DateRange) => void; min?: string; max?: string
  label?: string; placeholder?: string; size?: 'sm' | 'md'
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(value)
  const [hover, setHover] = useState<string | null>(null)
  const [month, setMonth] = useState(() => new Date())
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const presets = rangePresets()
  const same = (x: DateRange, y: DateRange) => x.from === y.from && x.to === y.to

  const commit = useCallback((r: DateRange) => { if (r.from !== value.from || r.to !== value.to) onChange(r) }, [value, onChange])
  // Closing keeps what's picked so far, so a lone first day becomes "From <day>".
  const close = useCallback((reason: DismissReason) => {
    setOpen(false); commit(draft)
    if (reason === 'escape') trigger.current?.focus()
  }, [commit, draft])
  useDismiss(open, root, close)

  const show = () => {
    if (open) return close('outside')
    setDraft(value); setHover(null)
    setMonth(value.to ? parseDay(value.to) : value.from ? parseDay(value.from) : new Date())
    setOpen(true)
  }
  const apply = (r: DateRange) => { setDraft(r); commit(r); setOpen(false) }
  const pick = (k: string) => {
    if (!draft.from || draft.to || k < draft.from) return setDraft({ from: k, to: '' })
    apply({ from: draft.from, to: k })
    trigger.current?.focus()
  }
  // While choosing the last day, the band follows the pointer.
  const previewEnd = draft.from && !draft.to && hover && hover >= draft.from ? hover : draft.to || undefined
  const presetName = presets.find((p) => p.range.from && same(p.range, value))?.label

  return (
    <div ref={root} className="relative inline-block">
      <Trigger buttonRef={trigger} open={open} label={label} placeholder={placeholder} size={size}
        text={presetName ?? formatRange(value)} onClear={value.from || value.to ? () => onChange({ from: '', to: '' }) : undefined}
        onOpen={show} />
      {open && (
        <Popover label={label}>
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="flex flex-wrap gap-1.5 sm:w-32 sm:flex-col sm:flex-nowrap sm:gap-0.5 sm:border-r sm:border-slate-100 sm:pr-3">
              {presets.map((p) => {
                const active = same(p.range, draft)
                return (
                  <button key={p.label} type="button" aria-pressed={active} onClick={() => apply(p.range)}
                    className={`rounded-full px-3 py-1.5 text-left text-sm transition max-sm:ring-1 max-sm:ring-inset max-sm:ring-slate-200 sm:rounded-lg ${
                      active ? 'bg-brand-50 font-medium text-brand-700 max-sm:ring-brand-300' : 'text-slate-700 hover:bg-slate-900/[0.05]'}`}>
                    {p.label}
                  </button>
                )
              })}
            </div>
            <div>
              <Calendar month={month} onMonth={setMonth} start={draft.from || undefined} end={previewEnd}
                onPick={pick} onHover={setHover} min={min} max={max} />
              <div className="mt-3 flex items-center justify-between gap-2 border-t border-slate-100 pt-3">
                <span className="text-xs text-slate-500">
                  {draft.from && !draft.to ? 'Now pick the last day' : formatRange(draft) ?? 'Pick the first day'}
                </span>
                <button type="button" className="btn-ghost btn-xs" disabled={!draft.from && !draft.to} onClick={() => apply({ from: '', to: '' })}>Clear</button>
              </div>
            </div>
          </div>
        </Popover>
      )}
    </div>
  )
}
