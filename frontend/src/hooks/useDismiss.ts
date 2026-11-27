import { useEffect, type RefObject } from 'react'

export type DismissReason = 'outside' | 'escape'

/** Closes a popover on a click outside `ref` or on Escape. Clicks in floating layers rendered elsewhere in the page
 *  (`data-floating`, e.g. an open dropdown's menu) don't count as outside: the dropdown may live inside this popover. */
export function useDismiss(open: boolean, ref: RefObject<HTMLElement | null>, close: (reason: DismissReason) => void) {
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      const t = e.target as Element
      if (!ref.current?.contains(t) && !t.closest?.('[data-floating]')) close('outside')
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close('escape') }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open, ref, close])
}
