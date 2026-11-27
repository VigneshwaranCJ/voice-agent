import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'

type Tone = 'success' | 'error'
interface Toast { id: number; text: string; tone: Tone }

const Ctx = createContext<(text: string, tone?: Tone) => void>(() => {})

/** Short confirmation messages ("Saved", "User added") in the bottom-right corner. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const next = useRef(1)
  const show = useCallback((text: string, tone: Tone = 'success') => {
    const id = next.current++
    setToasts((t) => [...t.slice(-3), { id, text, tone }])
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'error' ? 6000 : 3000)
  }, [])
  return (
    <Ctx.Provider value={show}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-4 bottom-4 z-[60] flex flex-col items-stretch gap-2 pb-[env(safe-area-inset-bottom)] sm:inset-x-auto sm:bottom-6 sm:right-6 sm:items-end">
        {toasts.map((t) => (
          <div key={t.id} role="status"
            className={`animate-rise pointer-events-auto flex max-w-sm items-center gap-2 rounded-2xl px-4 py-3 text-sm shadow-[var(--shadow-float)] ring-1 ${
              t.tone === 'success' ? 'bg-white text-slate-800 ring-black/5' : 'bg-rose-50 text-rose-700 ring-rose-200'}`}>
            <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${t.tone === 'success' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}

export const useToast = () => useContext(Ctx)
