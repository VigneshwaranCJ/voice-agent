import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'

export interface SelectOption { value: string; label: string }

const GAP = 6     // between the field and its menu
const EDGE = 8    // keep the menu this far from the window edges
const MAX_H = 288 // tallest menu before it scrolls

/**
 * A dropdown that matches the app's inputs: the field looks like `.input`, and its menu has the same rounded
 * corners. The menu is portalled to <body> with fixed positioning, so cards and scrolling tables never clip it,
 * and it opens upwards when there's no room below.
 *
 * Keyboard (WAI-ARIA select-only combobox): focus stays on the field; ↑/↓ move, Home/End jump, Enter or Space
 * picks, Escape closes, typing letters jumps to the matching option.
 */
export function Select({ value, onChange, options, id, label, placeholder = 'Select…', size = 'md', className = '', disabled }: {
  value: string; onChange: (v: string) => void; options: SelectOption[]
  id?: string        // pair with <label htmlFor={id}>
  label?: string     // accessible name when there's no visible <label>
  placeholder?: string; size?: 'sm' | 'md'; className?: string; disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [pos, setPos] = useState<CSSProperties | null>(null)
  const field = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLUListElement>(null)
  const typed = useRef({ text: '', at: 0 })
  const listId = useId()
  const selected = options.findIndex((o) => o.value === value)
  const current = options[selected]

  const show = (index = selected) => { setActive(index >= 0 ? index : 0); setOpen(true) }
  const hide = useCallback(() => { setOpen(false); setPos(null) }, [])
  const choose = (i: number) => {
    const o = options[i]
    if (!o) return
    hide()
    if (o.value !== value) onChange(o.value)
  }

  const place = useCallback(() => {
    const f = field.current?.getBoundingClientRect()
    const m = menu.current
    if (!f || !m) return
    const height = Math.min(m.scrollHeight, MAX_H)
    const width = Math.max(f.width, m.offsetWidth)
    const below = window.innerHeight - f.bottom - GAP - EDGE
    const above = f.top - GAP - EDGE
    const up = below < height && above > below
    setPos({
      // clientWidth, not innerWidth: Android Chrome widens innerWidth to take in anything overflowing the page
      left: Math.max(EDGE, Math.min(f.left, document.documentElement.clientWidth - EDGE - width)),
      minWidth: f.width,
      maxHeight: Math.max(120, Math.min(MAX_H, up ? above : below)),
      ...(up ? { bottom: window.innerHeight - f.top + GAP } : { top: f.bottom + GAP }),
    })
  }, [])

  useLayoutEffect(() => { if (open) place() }, [open, place])
  useEffect(() => {
    if (!open) return
    const down = (e: MouseEvent) => {
      const t = e.target as Node
      if (!field.current?.contains(t) && !menu.current?.contains(t)) hide()
    }
    document.addEventListener('mousedown', down)
    window.addEventListener('scroll', place, true) // follow the field when the page or a container scrolls
    window.addEventListener('resize', place)
    return () => {
      document.removeEventListener('mousedown', down)
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open, hide, place])
  useEffect(() => {
    if (open && pos && active >= 0) menu.current?.children[active]?.scrollIntoView({ block: 'nearest' })
  }, [open, pos, active])

  const onKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    const last = options.length - 1
    if (!open) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
        e.preventDefault()
        show(selected < 0 && e.key === 'ArrowUp' ? last : selected)
        return
      }
    } else {
      const moves: Record<string, number> = {
        ArrowDown: Math.min(last, active + 1), ArrowUp: Math.max(0, active - 1),
        Home: 0, PageUp: 0, End: last, PageDown: last,
      }
      if (e.key in moves) { e.preventDefault(); setActive(moves[e.key]); return }
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(active); return }
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); hide(); return } // don't also close a parent menu
      if (e.key === 'Tab') { hide(); return }
    }
    // Type to jump: a repeated first letter cycles through matches; a quick word matches by prefix.
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const t = typed.current, now = Date.now()
      t.text = (now - t.at < 600 ? t.text : '') + e.key.toLowerCase()
      t.at = now
      const cycling = [...t.text].every((c) => c === t.text[0]) // "w", "ww", "www" step through the W options
      const query = cycling ? t.text[0] : t.text
      const from = open ? active : selected
      const step = cycling ? 1 : 0
      for (let n = 0; n < options.length; n++) {
        const i = (from + step + n + options.length) % options.length
        if (options[i].label.toLowerCase().startsWith(query)) { if (open) setActive(i); else show(i); break }
      }
    }
  }

  return (
    <>
      <button ref={field} id={id} type="button" role="combobox" disabled={disabled}
        aria-label={label} aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? listId : undefined}
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        onClick={() => (open ? hide() : show())} onKeyDown={onKey}
        className={`input ${size === 'sm' ? 'input-sm' : ''} inline-flex cursor-pointer items-center justify-between gap-2 text-left disabled:cursor-not-allowed disabled:opacity-50 ${className}`}>
        <span className={`truncate ${current ? '' : 'text-slate-500'}`}>{current?.label ?? placeholder}</span>
        <svg viewBox="0 0 24 24" className={`h-4 w-4 shrink-0 text-slate-500 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
          fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="m6 9 6 6 6-6" /></svg>
      </button>
      {open && createPortal(
        <ul ref={menu} id={listId} role="listbox" data-floating="" aria-label={label} aria-labelledby={label ? undefined : id}
          style={pos ?? { top: 0, left: 0, visibility: 'hidden' }}
          className="animate-pop fixed z-[70] overflow-y-auto overscroll-contain rounded-xl bg-white p-1.5 shadow-[var(--shadow-float)] ring-1 ring-black/5">
          {options.map((o, i) => {
            const isSelected = o.value === value
            return (
              <li key={o.value} id={`${listId}-${i}`} role="option" aria-selected={isSelected}
                onMouseDown={(e) => e.preventDefault()} // keep focus on the field
                onMouseEnter={() => setActive(i)} onClick={() => choose(i)}
                className={`flex cursor-pointer items-center justify-between gap-4 whitespace-nowrap rounded-lg px-3 py-2 text-sm transition-colors ${
                  i === active ? 'bg-slate-100' : ''} ${isSelected ? 'font-medium text-brand-600' : 'text-slate-700'}`}>
                <span>{o.label}</span>
                <svg viewBox="0 0 24 24" className={`h-4 w-4 shrink-0 ${isSelected ? '' : 'invisible'}`} fill="none" stroke="currentColor"
                  strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M20 6 9 17l-5-5" /></svg>
              </li>
            )
          })}
        </ul>,
        document.body,
      )}
    </>
  )
}
