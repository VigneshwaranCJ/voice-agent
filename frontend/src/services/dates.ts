/* Days are local calendar dates as 'YYYY-MM-DD' strings (the format <input type="date"> used), so they
   compare correctly as plain strings. */
const pad = (n: number) => String(n).padStart(2, '0')
export const dayKey = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
export const parseDay = (k: string) => { const [y, m, d] = k.split('-').map(Number); return new Date(y, m - 1, d) }
export const todayKey = () => dayKey(new Date())
export const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)
export const addMonths = (d: Date, n: number) => {
  const first = new Date(d.getFullYear(), d.getMonth() + n, 1)
  const last = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate()
  return new Date(first.getFullYear(), first.getMonth(), Math.min(d.getDate(), last))
}
export const clampKey = (k: string, min?: string, max?: string) => (min && k < min ? min : max && k > max ? max : k)
export const fmt = (k: string, opts: Intl.DateTimeFormatOptions) => parseDay(k).toLocaleDateString(undefined, opts)
export const formatDay = (k: string) => fmt(k, { day: 'numeric', month: 'short', year: 'numeric' })

export interface DateRange { from: string; to: string } // '' = open-ended on that side

export function formatRange({ from, to }: DateRange): string | null {
  if (!from && !to) return null
  if (!to) return `From ${formatDay(from)}`
  if (!from) return `Until ${formatDay(to)}`
  if (from === to) return formatDay(from)
  const sameYear = from.slice(0, 4) === to.slice(0, 4)
  return `${fmt(from, sameYear ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: 'numeric' })} – ${formatDay(to)}`
}
