import { useEffect, useRef, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { api, session } from '../services/api'
import type { ToolInfo } from '../types'
import { startSarvamCall, type CallHandle, type CallStatus } from '../voice/sarvamCall'
import { useToast } from './Toast'
import { ErrorNote } from './ui'

interface Ids { org_id: string; workspace_id: string; app_id: string }
interface Link extends Ids {
  linked: boolean; enabled: boolean; has_token: boolean; tool_url: string
  effective: Ids            // own value, else the server's SARVAM_AGENTS_*_ID default
  voice_configured: boolean // SARVAM_AGENTS_API_KEY is set on the server
}
interface CheckResult {
  connected: boolean; interaction_id: string | null; agent_spoke: boolean; agent_audio_ms: number
  first_agent_text: string | null; error: string | null; seconds: number
}

/**
 * Connects this agent to a hosted Sarvam Voice Agent (Samvaad). Sarvam runs the call and calls back our
 * read-only tools with the token created here; bookings stay off on that channel until confirmation is solved.
 */
export default function SarvamLink({ agentId, enabledTools, catalog }:
  { agentId: string; enabledTools: string[]; catalog: ToolInfo[] | null }) {
  const toast = useToast()
  const { data, error, setData } = useApi<Link>(`/agents/${agentId}/sarvam`)
  const [form, setForm] = useState({ org_id: '', workspace_id: '', app_id: '', enabled: false })
  const [token, setToken] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [call, setCall] = useState<{ status: CallStatus; lines: { role: string; text: string }[]; error?: string; saved?: string } | null>(null)
  const handle = useRef<CallHandle | null>(null)
  const starting = useRef(false) // one call at a time, even on a double click
  const [check, setCheck] = useState<CheckResult | 'running' | null>(null)

  useEffect(() => {
    if (data) setForm({ org_id: data.org_id, workspace_id: data.workspace_id, app_id: data.app_id, enabled: data.enabled })
  }, [data])
  useEffect(() => () => { handle.current?.stop() }, []) // hang up when leaving the page
  if (!data) return <ErrorNote error={error} />

  const live = call && (call.status === 'connecting' || call.status === 'listening' || call.status === 'speaking')
  const eff = data.effective
  const callable = data.voice_configured && data.enabled && eff.org_id && eff.workspace_id && eff.app_id
  // Sarvam needs a moment to finish the transcript; retry a few times, then point to Calls.
  const saveTranscript = async (interactionId: string) => {
    for (const wait of [3000, 10000, 30000, 60000]) {
      await new Promise((r) => setTimeout(r, wait))
      try {
        const r = await api<{ pending: boolean }>(`/agents/${agentId}/sarvam/calls`, { method: 'POST', json: { interaction_id: interactionId } })
        if (!r.pending) { setCall((c) => c && { ...c, saved: 'Transcript saved under Calls.' }); return }
      } catch (e) { setCall((c) => c && { ...c, saved: `Couldn't save the transcript: ${(e as Error).message}` }); return }
    }
    setCall((c) => c && { ...c, saved: 'The transcript isn’t ready yet. Open the call under Calls and use “Refresh transcript”.' })
  }
  const testCall = async () => {
    if (handle.current) { const h = handle.current; handle.current = null; await h.stop(); return }
    if (starting.current) return
    starting.current = true
    setCall({ status: 'connecting', lines: [] })
    try {
      const ids = await api<Ids & { agent_variables?: Record<string, string> }>(`/agents/${agentId}/sarvam/call-config`)
      const headers: Record<string, string> = { Authorization: `Bearer ${session.token}` }
      if (session.tenantId) headers['X-Tenant-ID'] = session.tenantId
      handle.current = await startSarvamCall({
        ids,
        baseUrl: `/api/v1/sarvam/runtime/${encodeURIComponent(agentId)}/`,
        headers,
        onStatus: (status) => {
          if (status === 'ended' || status === 'error') handle.current = null
          setCall((c) => ({ lines: [], ...c, status }))
        },
        onTranscript: (role, text) => setCall((c) => c && { ...c, lines: [...c.lines, { role, text }] }),
        onInterrupt: () => setCall((c) => c && { ...c, lines: [...c.lines, { role: 'system', text: '(you interrupted — the agent stopped and is listening)' }] }),
        onError: (msg) => setCall((c) => ({ lines: [], ...c, status: 'error', error: msg })),
        onFinished: (interactionId) => { void saveTranscript(interactionId) },
      })
    } catch (e) {
      handle.current = null
      setCall((c) => (c && c.status === 'connecting' ? { ...c, status: 'error', error: (e as Error).message } : c))
    } finally { starting.current = false }
  }
  const runCheck = async () => {
    setCheck('running')
    try { setCheck(await api<CheckResult>(`/agents/${agentId}/sarvam/check`, { method: 'POST' })) }
    catch (e) { setCheck(null); toast((e as Error).message, 'error') }
  }

  const readTools = (catalog ?? []).filter((t) => enabledTools.includes(t.name) && !t.is_write)
  const save = async () => {
    setBusy(true)
    try { setData(await api<Link>(`/agents/${agentId}/sarvam`, { method: 'PUT', json: form })); toast('Sarvam link saved') }
    catch (e) { toast((e as Error).message, 'error') }
    finally { setBusy(false) }
  }
  const rotate = async () => {
    if (data.has_token && !confirm('Create a new token? The old one stops working at once.')) return
    setBusy(true)
    try {
      const r = await api<Link & { token: string }>(`/agents/${agentId}/sarvam/token`, { method: 'POST' })
      const { token: t, ...link } = r
      setData(link); setToken(t)
    } catch (e) { toast((e as Error).message, 'error') }
    finally { setBusy(false) }
  }
  const copy = async (text: string) => {
    try { await navigator.clipboard.writeText(text); toast('Copied') } catch { toast('Copy failed', 'error') }
  }

  return (
    <div className="card">
      <div className="mb-1 text-sm font-semibold">Sarvam Voice Agent (hosted calls)</div>
      <p className="mb-3 text-xs text-slate-500">
        Let a Sarvam Voice Agent answer calls while using this business's data. In Sarvam, add an API tool per tool
        below: method <code>POST</code>, auth <b>Bearer</b> with the token from here, body = the tool's arguments as
        JSON. Optionally send the call's Interaction ID in an <code>X-Interaction-Id</code> header. Bookings aren't
        available on this channel yet.
      </p>
      {!data.voice_configured && (
        <div className="mb-3 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800 ring-1 ring-inset ring-amber-200">
          Voice calls are off on this server: set <code>SARVAM_AGENTS_API_KEY</code> (Sarvam → Settings → API key) and restart.
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-3">
        {(['org_id', 'workspace_id', 'app_id'] as const).map((k) => (
          <div key={k}>
            <label className="label">{k === 'org_id' ? 'Org ID' : k === 'workspace_id' ? 'Workspace ID' : 'App ID (agent ID)'}</label>
            <input className="input" value={form[k]} placeholder={eff[k] && !form[k] ? `${eff[k]} (server default)` : ''}
              onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
          </div>
        ))}
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
        Accept tool calls from Sarvam for this agent
      </label>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="btn" disabled={busy} onClick={save}>Save</button>
        <button className="btn-ghost" disabled={busy} onClick={rotate}>{data.has_token ? 'Replace tool token' : 'Create tool token'}</button>
        <button className="btn-ghost" disabled={!callable} onClick={testCall}
          title={callable ? 'Talk to this agent through Sarvam (needs your microphone)' : 'Set the voice key on the server, save the Sarvam ids and tick “Accept tool calls” first'}>
          {live ? 'End test call' : 'Test call'}
        </button>
        <button className="btn-ghost" disabled={!data.voice_configured || !eff.app_id || check === 'running'} onClick={runCheck}
          title="The server opens a short call with Sarvam's Python SDK and waits for the greeting (uses a few seconds of call time)">
          {check === 'running' ? 'Checking…' : 'Check connection'}
        </button>
      </div>
      {check && check !== 'running' && (
        <div className={`mt-3 rounded-xl px-3 py-2 text-xs ring-1 ring-inset ${check.connected && check.agent_spoke && !check.error ? 'bg-emerald-50 text-emerald-800 ring-emerald-200' : 'bg-red-50 text-red-800 ring-red-200'}`}>
          <div className="font-semibold">
            {check.connected && check.agent_spoke && !check.error ? 'Connected — the agent answered' : check.connected ? 'Connected, but…' : 'Couldn’t connect'}
            <span className="font-normal text-slate-500"> · {check.seconds}s</span>
          </div>
          {check.error && <div className="mt-1">{check.error}</div>}
          {check.first_agent_text && <div className="mt-1">Agent said: “{check.first_agent_text}”</div>}
          {check.agent_audio_ms > 0 && <div className="mt-1 text-slate-600">Received {(check.agent_audio_ms / 1000).toFixed(1)} s of agent audio.</div>}
        </div>
      )}
      {call && (
        <div className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-xs ring-1 ring-inset ring-slate-200">
          <div className="font-semibold">
            {call.status === 'connecting' ? 'Connecting…' : call.status === 'listening' ? 'Listening — speak now'
              : call.status === 'speaking' ? 'Agent speaking…' : call.status === 'error' ? 'Call failed' : 'Call ended'}
          </div>
          {call.error && <div className="mt-1 text-red-700">{call.error}</div>}
          {call.saved && <div className="mt-1 text-slate-600">{call.saved}</div>}
          {call.lines.map((l, i) => (
            l.role === 'system'
              ? <div key={i} className="mt-1 italic text-slate-500">{l.text}</div>
              : <div key={i} className="mt-1"><span className="font-medium">{/user/i.test(l.role) ? 'You' : 'Agent'}:</span> {l.text}</div>
          ))}
        </div>
      )}
      {token && (
        <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900 ring-1 ring-inset ring-amber-200">
          <div className="mb-1 font-semibold">Tool token — shown once. Paste it into Sarvam's Bearer auth now.</div>
          <code className="break-all">{token}</code>
          <div className="mt-2"><button className="btn-ghost" onClick={() => copy(token)}>Copy token</button></div>
        </div>
      )}
      {readTools.length > 0 && (
        <div className="mt-4">
          <div className="label">Tool URLs</div>
          <ul className="space-y-1 text-xs">
            {readTools.map((t) => {
              const url = data.tool_url.replace('TOOL_NAME', t.name)
              return (
                <li key={t.name} className="flex items-start gap-2">
                  <button className="btn-ghost shrink-0 px-2 py-0.5" onClick={() => copy(url)}>Copy</button>
                  <span><code className="break-all">{url}</code><br /><span className="text-slate-500">{t.description}</span></span>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
