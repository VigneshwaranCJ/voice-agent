import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import ChangePasswordDialog from '../components/ChangePasswordDialog'
import { Select } from '../components/Select'
import { useAuth } from '../hooks/useAuth'
import { useDismiss } from '../hooks/useDismiss'

/** 24px line icons for navigation (stroke = currentColor). */
const icon = (children: ReactNode) => (
  <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] shrink-0" fill="none" stroke="currentColor" strokeWidth="1.9"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden>{children}</svg>
)
const NavIcons = {
  overview: icon(<><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></>),
  agents: icon(<><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>),
  knowledge: icon(<><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" /><path d="M4 19V5M8 7h7M8 11h5" /></>),
  calls: icon(<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" />),
  followups: icon(<><path d="M9 11l3 3 8-8" /><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9" /></>),
  data: icon(<><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>),
  integrations: icon(<><path d="M9 7V3M15 7V3M7 7h10v4a5 5 0 0 1-10 0z" /><path d="M12 16v5" /></>),
  business: icon(<><path d="M4 21V7l8-4 8 4v14" /><path d="M9 21v-6h6v6M9 10h.01M15 10h.01" /></>),
  team: icon(<><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18.5 20a6.5 6.5 0 0 0-3-5.5" /></>),
  businesses: icon(<><rect x="3" y="7" width="18" height="14" rx="2" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18" /></>),
}

interface Item { to: string; label: string; icon: ReactNode; end?: boolean; group: 'Workspace' | 'Activity' | 'Settings'; primary?: boolean }

function navItems(isAdmin: boolean, isPlatform: boolean): Item[] {
  return [
    { to: '/', label: 'Overview', icon: NavIcons.overview, end: true, group: 'Workspace', primary: true },
    { to: '/agents', label: 'Agents', icon: NavIcons.agents, group: 'Workspace', primary: true },
    { to: '/knowledge', label: 'Knowledge', icon: NavIcons.knowledge, group: 'Workspace', primary: true },
    { to: '/calls', label: 'Calls', icon: NavIcons.calls, group: 'Activity', primary: true },
    { to: '/follow-ups', label: 'Follow-ups', icon: NavIcons.followups, group: 'Activity', primary: true },
    { to: '/data', label: 'Data', icon: NavIcons.data, group: 'Activity' },
    { to: '/business', label: 'Business profile', icon: NavIcons.business, group: 'Settings' },
    { to: '/integrations', label: 'Integrations', icon: NavIcons.integrations, group: 'Settings' },
    ...(isAdmin ? [{ to: '/team', label: 'Team', icon: NavIcons.team, group: 'Settings' as const }] : []),
    ...(isPlatform ? [{ to: '/tenants', label: 'All businesses', icon: NavIcons.businesses, group: 'Settings' as const }] : []),
  ]
}

const isActive = (item: Item, path: string) => (item.end ? path === item.to : path === item.to || path.startsWith(`${item.to}/`))

function Logo() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <rect x="3" y="9" width="2.6" height="6" rx="1.3" fill="currentColor" />
      <rect x="7.6" y="5" width="2.6" height="14" rx="1.3" fill="currentColor" />
      <rect x="12.2" y="7.5" width="2.6" height="9" rx="1.3" fill="currentColor" />
      <rect x="16.8" y="3.5" width="2.6" height="17" rx="1.3" fill="currentColor" />
    </svg>
  )
}

function PickBusiness({ hasAny, onOpenMenu }: { hasAny: boolean; onOpenMenu: () => void }) {
  return (
    <div className="card mx-auto max-w-xl py-12 text-center">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
        {hasAny ? 'Choose a business' : 'Create your first business'}
      </h1>
      <p className="mx-auto mt-3 max-w-md text-base leading-relaxed text-slate-500">
        {hasAny
          ? 'Agents, calls, knowledge and data belong to a business. Pick one from the account menu to manage it.'
          : 'Agents, calls, knowledge and data belong to a business. Add one to get started, then create its voice agent under Agents.'}
      </p>
      <div className="mt-6">
        {hasAny
          ? <button className="btn" onClick={onOpenMenu}>Choose business</button>
          : <NavLink to="/tenants" className="btn">Create a business</NavLink>}
      </div>
    </div>
  )
}

const DESKTOP = '(min-width: 1024px)'

export default function AppLayout() {
  const { user, tenants, tenantId, setTenantId, logout } = useAuth()
  const isPlatform = user?.role === 'platform_admin'
  const isAdmin = isPlatform || user?.role === 'tenant_admin'
  const [account, setAccount] = useState(false)
  const [more, setMore] = useState(false)
  const [drawer, setDrawer] = useState(false)
  const [changingPassword, setChangingPassword] = useState(false)
  const closePasswordDialog = useCallback(() => setChangingPassword(false), [])
  const accountRef = useRef<HTMLDivElement>(null)
  const moreRef = useRef<HTMLDivElement>(null)
  const burgerRef = useRef<HTMLButtonElement>(null)
  const scroller = useRef<HTMLElement>(null)
  const loc = useLocation()

  const closeAccount = useCallback(() => setAccount(false), [])
  const closeMore = useCallback(() => setMore(false), [])
  useDismiss(account, accountRef, closeAccount)
  useDismiss(more, moreRef, closeMore)
  useEffect(() => { setAccount(false); setMore(false); setDrawer(false) }, [loc.pathname])
  // The page scrolls inside <main> (so its scrollbar stays below the navbar). Each page starts at the top, and focus
  // moves into the scrolling area unless it's already there, so Space / Page Down / arrow keys scroll the page.
  useEffect(() => {
    const el = scroller.current
    if (!el) return
    el.scrollTo(0, 0)
    window.scrollTo(0, 0) // phones scroll the window instead
    if (!el.contains(document.activeElement)) el.focus({ preventScroll: true })
  }, [loc.pathname, tenantId])
  // Leaving phone size with the drawer open (rotate, resize) would strand it: close it.
  useEffect(() => {
    const mq = window.matchMedia(DESKTOP)
    const onChange = () => { if (mq.matches) setDrawer(false) }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  // Every page except Businesses and Team works on one business; a platform admin must have one selected first.
  const needsBusiness = isPlatform && !tenantId && !['/tenants', '/team'].includes(loc.pathname)
  const items = navItems(isAdmin, isPlatform)
  const primary = items.filter((i) => i.primary)
  const secondary = items.filter((i) => !i.primary)
  const activeSecondary = secondary.find((i) => isActive(i, loc.pathname))
  const initials = (user?.full_name || user?.email || '?').slice(0, 1).toUpperCase()
  const businessName = isPlatform ? tenants.find((t) => t.id === tenantId)?.name ?? 'Platform' : user?.tenant_name ?? ''
  const openChooser = () => (window.matchMedia(DESKTOP).matches ? setAccount(true) : setDrawer(true))

  const businessSwitch = (id: string) => isPlatform && (
    <div>
      <label className="label" htmlFor={id}>Business</label>
      <Select id={id} value={tenantId ?? ''} onChange={setTenantId} placeholder="Choose a business…"
        options={tenants.map((t) => ({ value: t.id, label: t.name }))} />
    </div>
  )

  return (
    <div className="min-h-dvh lg:flex lg:h-dvh lg:flex-col">
      {/* Desktop: only <main> scrolls, so its scrollbar starts below the navbar. Phones and tablets scroll the whole
          page as usual (the navbar is sticky), which keeps native behaviour: the address bar collapses and tapping the
          status bar scrolls to the top. */}
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-xl focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:shadow">
        Skip to content
      </a>
      <header className="glass sticky top-0 z-30 shrink-0 border-b lg:relative border-black/[0.06] shadow-[0_1px_0_rgb(255_255_255/0.6)_inset]">
        <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:gap-6 lg:px-8">
          <NavLink to="/" className="flex shrink-0 items-center gap-2 text-slate-900" aria-label="VoiceCare home">
            <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-gradient-to-br from-brand-500 to-[#8e5cf7] text-white"><Logo /></span>
            <span className="text-base font-bold tracking-tight">VoiceCare</span>
          </NavLink>

          {/* Desktop: main sections inline, the rest under More. */}
          <nav aria-label="Main" className="hidden min-w-0 flex-1 items-center gap-0.5 lg:flex">
            {primary.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end}
                className={({ isActive: a }) => `whitespace-nowrap rounded-full px-3.5 py-2 text-sm transition-colors duration-200 ${a ? 'bg-slate-900/[0.07] font-medium text-slate-900' : 'text-slate-600 hover:bg-slate-900/[0.04] hover:text-slate-900'}`}>
                {n.label}
              </NavLink>
            ))}
            <div ref={moreRef} className="relative">
              <button onClick={() => setMore((v) => !v)} aria-expanded={more} aria-haspopup="menu"
                className={`flex cursor-pointer items-center gap-1 whitespace-nowrap rounded-full px-3.5 py-2 text-sm transition-colors duration-200 ${activeSecondary ? 'bg-slate-900/[0.07] font-medium text-slate-900' : 'text-slate-600 hover:bg-slate-900/[0.04] hover:text-slate-900'}`}>
                {activeSecondary?.label ?? 'More'}
                <svg viewBox="0 0 24 24" className={`h-3.5 w-3.5 transition-transform ${more ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden><path d="m6 9 6 6 6-6" /></svg>
              </button>
              {more && (
                <div role="menu" className="glass animate-rise absolute left-0 mt-2 w-60 rounded-2xl p-1.5 shadow-[var(--shadow-float)] ring-1 ring-black/5" style={{ animationDuration: '0.3s' }}>
                  {secondary.map((n) => (
                    <NavLink key={n.to} to={n.to} role="menuitem"
                      className={({ isActive: a }) => `flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition ${a ? 'bg-slate-900/[0.06] font-medium text-slate-900' : 'text-slate-700 hover:bg-slate-900/[0.05]'}`}>
                      <span className="text-slate-500">{n.icon}</span>{n.label}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          </nav>

          <div className="flex-1 lg:hidden" />

          {/* Account menu (desktop). */}
          <div ref={accountRef} className="relative hidden lg:block">
            <button onClick={() => setAccount((v) => !v)} aria-expanded={account} aria-haspopup="menu" aria-label="Account menu"
              className="flex cursor-pointer items-center gap-2 rounded-full py-1 pl-1 pr-3 text-sm text-slate-700 transition hover:bg-slate-900/[0.05]">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-violet-500 text-sm font-semibold text-white">{initials}</span>
              <span className="max-w-40 truncate">{businessName}</span>
            </button>
            {account && (
              <div role="menu" className="glass animate-rise absolute right-0 mt-2 w-72 rounded-2xl p-2 shadow-[var(--shadow-float)] ring-1 ring-black/5" style={{ animationDuration: '0.35s' }}>
                <div className="px-3 py-2">
                  <div className="truncate text-sm font-medium text-slate-900">{user?.email}</div>
                  <div className="mt-0.5 text-xs capitalize text-slate-500">{user?.role.replace('_', ' ')}</div>
                </div>
                {isPlatform && <div className="px-3 pb-2">{businessSwitch('tenant-switch')}</div>}
                <div className="my-1 h-px bg-black/5" />
                <button role="menuitem" onClick={() => { setAccount(false); setChangingPassword(true) }}
                  className="w-full rounded-xl px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-900/[0.05]">Change password</button>
                <button role="menuitem" onClick={logout} className="w-full rounded-xl px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-900/[0.05]">Sign out</button>
              </div>
            )}
          </div>

          {/* Phones & tablets: business name + menu button. */}
          <span className="min-w-0 max-w-[40vw] truncate text-sm text-slate-600 lg:hidden">{businessName}</span>
          <button ref={burgerRef} onClick={() => setDrawer(true)} aria-label="Open menu" aria-expanded={drawer} aria-controls="mobile-nav"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-slate-700 transition hover:bg-slate-900/[0.05] lg:hidden">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M4 7h16M4 12h16M4 17h16" /></svg>
          </button>
        </div>
      </header>

      <MobileDrawer open={drawer} onClose={() => { setDrawer(false); burgerRef.current?.focus() }} items={items} path={loc.pathname}
        header={<>
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-violet-500 text-sm font-semibold text-white">{initials}</span>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-slate-900">{user?.email}</div>
              <div className="truncate text-xs capitalize text-slate-500">{user?.role.replace('_', ' ')}{businessName && ` · ${businessName}`}</div>
            </div>
          </div>
          {isPlatform && <div className="mt-4">{businessSwitch('tenant-switch-mobile')}</div>}
        </>}
        footer={<>
          <button onClick={() => { setDrawer(false); setChangingPassword(true) }}
            className="w-full rounded-xl px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-900/[0.05]">Change password</button>
          <button onClick={logout} className="w-full rounded-xl px-3 py-2.5 text-left text-sm text-rose-600 hover:bg-rose-50">Sign out</button>
        </>} />

      {/* Content is left-aligned on the same edge as the logo and fills the width. Only this area scrolls, so the
          scrollbar starts below the navbar; the gutter is always reserved so pages don't shift sideways. */}
      <main id="main" ref={scroller} tabIndex={-1}
        className="px-4 pb-24 pt-6 outline-none sm:px-6 sm:pt-12 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:px-8 lg:[scrollbar-gutter:stable]">
        <div key={`${tenantId ?? 'none'}:${loc.pathname}`} className="animate-fade">
          {needsBusiness ? <PickBusiness hasAny={tenants.length > 0} onOpenMenu={openChooser} /> : <Outlet key={tenantId ?? 'none'} />}
        </div>
      </main>
      {changingPassword && <ChangePasswordDialog onClose={closePasswordDialog} />}
    </div>
  )
}

/** Slide-in navigation for phones and tablets, grouped by section. */
function MobileDrawer({ open, onClose, items, path, header, footer }: {
  open: boolean; onClose: () => void; items: Item[]; path: string; header: ReactNode; footer: ReactNode
}) {
  const panel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden' // the page behind doesn't scroll while the menu is open
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    window.setTimeout(() => panel.current?.querySelector<HTMLElement>('a[aria-current="page"], a')?.focus(), 50)
    return () => { document.body.style.overflow = prev; document.removeEventListener('keydown', onKey) }
  }, [open, onClose])
  const groups = (['Workspace', 'Activity', 'Settings'] as const).map((g) => [g, items.filter((i) => i.group === g)] as const)
  return (
    <div className={`fixed inset-0 z-40 lg:hidden ${open ? '' : 'pointer-events-none'}`} aria-hidden={!open}>
      <div onClick={onClose} className={`absolute inset-0 bg-slate-900/30 backdrop-blur-[2px] transition-opacity duration-300 ${open ? 'opacity-100' : 'opacity-0'}`} />
      <div ref={panel} id="mobile-nav" role="dialog" aria-modal="true" aria-label="Menu"
        className={`absolute inset-y-0 right-0 flex w-[min(20rem,88vw)] flex-col bg-white shadow-2xl transition-transform duration-300 ease-out ${open ? 'translate-x-0' : 'translate-x-full'}`}>
        <div className="flex items-start justify-between gap-3 border-b border-black/[0.06] p-4 pt-[max(1rem,env(safe-area-inset-top))]">
          <div className="min-w-0 flex-1">{header}</div>
          <button onClick={onClose} aria-label="Close menu" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-slate-600 hover:bg-slate-900/[0.05]" tabIndex={open ? 0 : -1}>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6 6 18" /></svg>
          </button>
        </div>
        <nav aria-label="Main" className="flex-1 overflow-y-auto overscroll-contain p-3">
          {groups.map(([g, list]) => !!list.length && (
            <div key={g} className="mb-3">
              <div className="section-label px-3 pb-1 pt-2">{g}</div>
              {list.map((n) => {
                const active = isActive(n, path)
                return (
                  <NavLink key={n.to} to={n.to} end={n.end} tabIndex={open ? 0 : -1} aria-current={active ? 'page' : undefined}
                    className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-base transition ${active ? 'bg-brand-50 font-medium text-brand-700' : 'text-slate-700 hover:bg-slate-900/[0.04]'}`}>
                    <span className={active ? 'text-brand-600' : 'text-slate-500'}>{n.icon}</span>{n.label}
                  </NavLink>
                )
              })}
            </div>
          ))}
        </nav>
        <div className="border-t border-black/[0.06] p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">{footer}</div>
      </div>
    </div>
  )
}
