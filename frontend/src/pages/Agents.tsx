import { useEffect, useState, type FormEvent } from 'react'
import SarvamLink from '../components/SarvamLink'
import { Select } from '../components/Select'
import TestChat from '../components/TestChat'
import { useToast } from '../components/Toast'
import { Badge, Empty, ErrorNote, PageHeader, SuccessNote, fmtDate } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../hooks/useAuth'
import { api } from '../services/api'
import { LANGUAGES, type Agent, type AgentConfig, type ToolInfo } from '../types'

export default function Agents() {
  const { user } = useAuth()
  const { data: agents, reload, error } = useApi<Agent[]>('/agents')
  const [selected, setSelected] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const canCreate = user?.role !== 'tenant_agent' // creating agents needs a business admin or platform admin
  useEffect(() => { if (agents?.length && !selected) setSelected(agents[0].id) }, [agents, selected])

  const created = (a: Agent) => { setCreating(false); setSelected(a.id); reload() }
  const newButton = canCreate && <button className="btn" onClick={() => setCreating(true)}>New agent</button>

  if (agents && !agents.length && !creating) {
    return (
      <div>
        <PageHeader eyebrow="Configure" title="Agents" subtitle="Each agent answers calls for this business in its own voice and languages." />
        <ErrorNote error={error} />
        <Empty>
          <div>This business has no agents yet.</div>
          {canCreate ? <div className="mt-4">{newButton}</div> : <div className="mt-1">Ask a business admin to create one.</div>}
        </Empty>
      </div>
    )
  }
  return (
    <div>
      <PageHeader eyebrow="Configure" title="Agents" subtitle="Personality, instructions, voice, languages and tools per agent. Saving creates a new config version."
        actions={!creating ? newButton : undefined} />
      <ErrorNote error={error} />
      {creating && <NewAgentForm onCreated={created} onCancel={() => setCreating(false)} />}
      <div className={creating ? 'hidden' : ''}>
        {/* Agent picker: a row above the editor, so the editor gets the full width. Scrolls sideways when there are many. */}
        <div role="group" aria-label="Choose an agent" className="-mx-1 mb-5 flex gap-3 overflow-x-auto px-1 pb-2 pt-1">
          {agents?.map((a) => {
            const on = selected === a.id
            return (
              <button key={a.id} onClick={() => setSelected(a.id)} aria-pressed={on}
                className={`flex shrink-0 cursor-pointer items-center gap-3 rounded-2xl bg-white py-2.5 pl-2.5 pr-5 text-left shadow-[var(--shadow-card)] transition ${
                  on ? 'ring-2 ring-brand-500' : 'ring-1 ring-black/5 hover:ring-slate-300'}`}>
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-[#8e5cf7] text-sm font-semibold text-white">{a.name.slice(0, 1)}</span>
                <span className="min-w-0">
                  <span className="block max-w-64 truncate text-sm font-semibold text-slate-900">{a.name}</span>
                  <span className="mt-1 flex gap-1.5"><Badge tone="blue">{a.industry.replace('_', ' ')}</Badge>{!a.is_active && <Badge tone="red">inactive</Badge>}</span>
                </span>
              </button>
            )
          })}
        </div>
        {selected && <AgentEditor key={selected} id={selected} onSaved={reload} />}
      </div>
    </div>
  )
}

function AgentEditor({ id, onSaved }: { id: string; onSaved: () => void }) {
  const { data: agent, error, setData, reload: reloadAgent } = useApi<Agent>(`/agents/${id}`)
  const toast = useToast()
  const { data: catalog } = useApi<ToolInfo[]>('/agents/tools/catalog')
  const { data: industries } = useApi<{ available: { key: string; default_tools: string[] }[] }>('/industries')
  const [cfg, setCfg] = useState<AgentConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { if (agent?.config) setCfg(agent.config) }, [agent])
  if (!agent || !cfg) return <ErrorNote error={error} />

  const allowed = industries?.available.find((i) => i.key === agent.industry)?.default_tools ?? []
  const tools = catalog?.filter((t) => allowed.includes(t.name)) ?? []

  const save = async () => {
    setSaving(true); setMsg(null); setErr(null)
    try {
      const { config: _c, id: _i, tenant_id: _t, created_at: _ca, ...rest } = agent
      const updated = await api<Agent>(`/agents/${id}`, { method: 'PUT', json: { ...rest, config: {
        persona_name: cfg.persona_name, personality: cfg.personality, system_instructions: cfg.system_instructions,
        greeting: cfg.greeting, enabled_tools: cfg.enabled_tools, workflows: cfg.workflows,
        escalation_policy: cfg.escalation_policy, llm_settings: cfg.llm_settings,
      } } })
      setData(updated)
      setMsg(`Saved — configuration version ${updated.config?.version}`)
      toast(`Saved as version ${updated.config?.version}`)
      onSaved()
    } catch (e) { setErr((e as Error).message) } finally { setSaving(false) }
  }

  const toggleLang = (code: string) => {
    const langs = agent.languages.includes(code) ? agent.languages.filter((l) => l !== code) : [...agent.languages, code]
    setData({ ...agent, languages: langs })
  }

  return (
    <div className="space-y-4">
      <ErrorNote error={err} />
      <SuccessNote>{msg}</SuccessNote>
      <div className="card grid grid-cols-1 gap-5 md:grid-cols-2">
        <div className="md:col-span-2"><h2 className="card-title">Agent details</h2></div>
        <div><label className="label">Agent name</label><input className="input" value={agent.name} onChange={(e) => setData({ ...agent, name: e.target.value })} /></div>
        <div><label className="label">Persona name (how the agent introduces itself)</label><input className="input" value={cfg.persona_name} onChange={(e) => setCfg({ ...cfg, persona_name: e.target.value })} /></div>
        <div className="md:col-span-2"><label className="label">Personality</label><textarea className="input h-24" value={cfg.personality} onChange={(e) => setCfg({ ...cfg, personality: e.target.value })} /></div>
        <div className="md:col-span-2"><label className="label">Business-specific instructions (added to industry defaults)</label>
          <textarea className="input h-32 font-mono text-[13px]" placeholder="e.g. Always mention free pickup for site visits. Never quote prices for Phase 2 units." value={cfg.system_instructions} onChange={(e) => setCfg({ ...cfg, system_instructions: e.target.value })} /></div>
        <div className="md:col-span-2">
          <span className="label">Languages</span>
          <div className="flex flex-wrap gap-2">
            {Object.entries(LANGUAGES).map(([code, name]) => (
              <label key={code} className="check-pill"><input type="checkbox" checked={agent.languages.includes(code)} onChange={() => toggleLang(code)} />{name}</label>
            ))}
          </div>
        </div>
        <div><label className="label" htmlFor="ag-default">Default language</label>
          <Select id="ag-default" value={agent.default_language} onChange={(default_language) => setData({ ...agent, default_language })}
            options={agent.languages.map((l) => ({ value: l, label: LANGUAGES[l] ?? l }))} /></div>
        <div className="flex flex-col justify-end gap-3 pb-1">
          <label className="check-row"><input type="checkbox" checked={agent.public_widget_enabled} onChange={(e) => setData({ ...agent, public_widget_enabled: e.target.checked })} />Allow public website widget</label>
          <label className="check-row"><input type="checkbox" checked={agent.is_active} onChange={(e) => setData({ ...agent, is_active: e.target.checked })} />Active</label>
        </div>
      </div>

      <div className="card">
        <h2 className="card-title">Greeting</h2>
        <p className="card-desc mb-4">What the agent says first, per language. Leave empty for the default.</p>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {agent.languages.map((l) => (
            <div key={l}><label className="label">{LANGUAGES[l] ?? l}</label>
              <input className="input" placeholder="Default greeting" value={cfg.greeting[l] ?? ''} onChange={(e) => setCfg({ ...cfg, greeting: { ...cfg.greeting, [l]: e.target.value } })} /></div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h2 className="card-title">Tools</h2>
            <p className="card-desc">What the agent may look up or do during a conversation.</p>
          </div>
          <span className="text-sm text-slate-500 tabular-nums">{tools.filter((t) => cfg.enabled_tools.includes(t.name)).length} of {tools.length} on</span>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {tools.map((t) => (
            <label key={t.name} className="check-card">
              <input type="checkbox" className="mt-px" checked={cfg.enabled_tools.includes(t.name)}
                onChange={(e) => setCfg({ ...cfg, enabled_tools: e.target.checked ? [...cfg.enabled_tools, t.name] : cfg.enabled_tools.filter((n) => n !== t.name) })} />
              <span className="min-w-0">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[13px] font-medium text-slate-900">{t.name}</span>
                  {t.requires_confirmation && <Badge tone="amber">confirms</Badge>}
                </span>
                <span className="mt-1 block text-sm leading-snug text-slate-500">{t.description}</span>
              </span>
            </label>
          ))}
        </div>
      </div>
      <div className="flex justify-end"><button className="btn" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button></div>
      <TestChat key={`${agent.id}:${cfg.version ?? ''}`} agentId={agent.id} languages={agent.languages} />
      <WidgetEmbed agentId={agent.id} enabled={agent.public_widget_enabled} />
      <SarvamLink agentId={agent.id} enabledTools={cfg.enabled_tools} catalog={catalog} />
      <ConfigHistory agentId={agent.id} current={cfg.version} onRestored={() => { reloadAgent(); onSaved() }} />
    </div>
  )
}

/** Creates an agent for the selected business; tools default to the industry's standard set on the server. */
function NewAgentForm({ onCreated, onCancel }: { onCreated: (a: Agent) => void; onCancel: () => void }) {
  const { tenants, tenantId } = useAuth()
  const { data: industries } = useApi<{ available: { key: string; label: string }[] }>('/industries')
  const businessIndustry = tenants.find((t) => t.id === tenantId)?.industry ?? 'custom'
  const [name, setName] = useState('')
  const [persona, setPersona] = useState('Priya')
  const [industry, setIndustry] = useState<string | null>(null)
  const [languages, setLanguages] = useState<string[]>(['en-IN', 'ta-IN'])
  const [defaultLanguage, setDefaultLanguage] = useState('en-IN')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  // Default to the business's own industry when it has a module; otherwise the generic one.
  const available = industries?.available ?? []
  const chosenIndustry = industry ?? (available.some((i) => i.key === businessIndustry) ? businessIndustry : 'custom')

  const toggleLang = (code: string) => {
    const next = languages.includes(code) ? languages.filter((l) => l !== code) : [...languages, code]
    setLanguages(next)
    if (!next.includes(defaultLanguage) && next.length) setDefaultLanguage(next[0])
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setErr(null)
    if (!languages.length) return setErr('Pick at least one language.')
    setBusy(true)
    try {
      const agent = await api<Agent>('/agents', { method: 'POST', json: {
        name: name.trim(), industry: chosenIndustry, languages, default_language: defaultLanguage,
        config: { persona_name: persona.trim() || 'Priya' },
      } })
      onCreated(agent)
    } catch (e2) { setErr((e2 as Error).message) } finally { setBusy(false) }
  }

  return (
    <form onSubmit={submit} className="card mb-6 space-y-5">
      <h2 className="card-title">New agent</h2>
      <ErrorNote error={err} />
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div><label className="label" htmlFor="na-name">Agent name</label>
          <input id="na-name" className="input" required maxLength={200} placeholder="e.g. Front desk" value={name} onChange={(e) => setName(e.target.value)} autoFocus /></div>
        <div><label className="label" htmlFor="na-persona">Persona name (how the agent introduces itself)</label>
          <input id="na-persona" className="input" maxLength={100} value={persona} onChange={(e) => setPersona(e.target.value)} /></div>
        <div><label className="label" htmlFor="na-industry">Industry</label>
          <Select id="na-industry" value={chosenIndustry} onChange={setIndustry} options={available.map((i) => ({ value: i.key, label: i.label }))} />
          <p className="hint">Sets the agent's tools and built-in instructions.</p></div>
        <div><label className="label" htmlFor="na-default">Default language</label>
          <Select id="na-default" value={defaultLanguage} onChange={setDefaultLanguage} options={languages.map((l) => ({ value: l, label: LANGUAGES[l] ?? l }))} /></div>
        <div className="md:col-span-2"><span className="label">Languages</span>
          <div className="flex flex-wrap gap-2">
            {Object.entries(LANGUAGES).map(([code, label]) => (
              <label key={code} className="check-pill"><input type="checkbox" checked={languages.includes(code)} onChange={() => toggleLang(code)} />{label}</label>
            ))}
          </div></div>
      </div>
      <p className="text-sm text-slate-500">After creating, you can set its personality, greetings, voice and tools here.</p>
      <div className="flex gap-2">
        <button type="submit" className="btn" disabled={busy || !name.trim()}>{busy ? 'Creating…' : 'Create agent'}</button>
        <button type="button" className="btn-ghost" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}

/** Every save creates a configuration version; restoring one saves it again as the newest version. */
function ConfigHistory({ agentId, current, onRestored }: { agentId: string; current?: number; onRestored: () => void }) {
  const { data: versions, reload } = useApi<AgentConfig[]>(`/agents/${agentId}/config/history`)
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<number | null>(null)
  useEffect(() => { reload() }, [current, reload])
  const restore = async (v: AgentConfig) => {
    if (!confirm(`Restore version ${v.version}? It becomes the newest version; nothing is deleted.`)) return
    setBusy(v.version ?? null)
    try {
      const saved = await api<AgentConfig>(`/agents/${agentId}/config`, { method: 'PUT', json: {
        persona_name: v.persona_name, personality: v.personality, system_instructions: v.system_instructions,
        greeting: v.greeting, enabled_tools: v.enabled_tools, workflows: v.workflows,
        escalation_policy: v.escalation_policy, llm_settings: v.llm_settings,
      } })
      toast(`Version ${v.version} restored as version ${saved.version}`)
      onRestored()
    } catch (e) { toast((e as Error).message, 'error') } finally { setBusy(null) }
  }
  return (
    <div className="card">
      <button className="flex w-full cursor-pointer items-center justify-between text-left" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span><span className="card-title">Version history</span>
          <span className="ml-2 text-sm text-slate-500">{versions ? `${versions.length} version${versions.length === 1 ? '' : 's'}` : ''}</span></span>
        <span className="flex items-center gap-1 text-sm font-medium text-brand-600">{open ? 'Hide' : 'Show'}
          <svg viewBox="0 0 24 24" className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="m6 9 6 6 6-6" /></svg></span>
      </button>
      {open && (
        <div className="mt-4 divide-y divide-slate-100">
          {versions?.map((v) => (
            <div key={v.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
              <span className="font-medium text-slate-900">v{v.version}</span>
              {v.version === current && <Badge tone="green">current</Badge>}
              <span className="text-slate-500">{fmtDate(v.created_at)}</span>
              <span className="min-w-0 flex-1 truncate text-slate-500">
                {v.persona_name} · {v.enabled_tools.length} tools{v.system_instructions ? ` · ${v.system_instructions.slice(0, 60)}` : ''}
              </span>
              {v.version !== current && (
                <button className="btn-ghost btn-sm" disabled={busy !== null} onClick={() => restore(v)}>{busy === v.version ? 'Restoring…' : 'Restore'}</button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** Copy-paste snippet that puts this agent's chat on the business's own website. */
function WidgetEmbed({ agentId, enabled }: { agentId: string; enabled: boolean }) {
  const toast = useToast()
  const snippet = `<script src="${window.location.origin}/widget.js" data-agent="${agentId}" async></script>`
  const copy = async () => {
    try { await navigator.clipboard.writeText(snippet); toast('Embed code copied') }
    catch { toast('Copy failed. Select the code and copy it manually.', 'error') }
  }
  return (
    <div className="card">
      <h2 className="card-title">Website widget</h2>
      <p className="card-desc mb-4">
        Paste this just before <code>&lt;/body&gt;</code> on your website. Visitors get a chat button that talks to this agent.
        Optional: <code>data-color="#0071e3"</code>, <code>data-title="Chat with us"</code>, <code>data-position="left"</code>.
      </p>
      {!enabled && (
        <div className="note note-amber mb-4">
          The widget is off for this agent. Tick “Allow public website widget” above and save to turn it on.
        </div>
      )}
      <pre className="overflow-x-auto rounded-xl bg-slate-900 p-4 font-mono text-[13px] leading-relaxed text-slate-100"><code>{snippet}</code></pre>
      <div className="mt-4 flex gap-2">
        <button className="btn" onClick={copy}>Copy code</button>
        <a className="btn-ghost" href={`/widget-demo.html?agent=${encodeURIComponent(agentId)}`} target="_blank" rel="noreferrer">Preview</a>
      </div>
    </div>
  )
}
