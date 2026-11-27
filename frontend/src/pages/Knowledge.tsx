import { useState } from 'react'
import { Badge, Empty, ErrorNote, PageHeader, fmtDate, statusTone } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'
import type { KnowledgeDoc } from '../types'

export default function Knowledge() {
  const { data: docs, reload, error } = useApi<KnowledgeDoc[]>('/knowledge/documents')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<{ title: string; score: number; content: string }[] | null>(null)

  const upload = async (file: File) => {
    setBusy(true); setErr(null)
    const fd = new FormData()
    fd.append('file', file)
    try { await api('/knowledge/documents/upload', { method: 'POST', body: fd }); reload() }
    catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const addText = async () => {
    setBusy(true); setErr(null)
    try { await api('/knowledge/documents/text', { method: 'POST', json: { title, text, source_type: 'faq' } }); setTitle(''); setText(''); reload() }
    catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const act = async (path: string, method: string) => {
    try { await api(path, { method }); reload() } catch (e) { setErr((e as Error).message) }
  }

  return (
    <div>
      <PageHeader eyebrow="Knowledge" title="Knowledge Base" subtitle="Documents, FAQs and policies the agent can search. Retrieval is scoped to this business only." />
      <ErrorNote error={err || error} />
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card">
          <h2 className="card-title">Upload document</h2>
          <p className="card-desc mb-4">PDF, DOCX, TXT, MD or CSV (max 15 MB).</p>
          <input type="file" className="block w-full max-w-full text-sm" accept=".pdf,.docx,.txt,.md,.csv" disabled={busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        </div>
        <div className="card space-y-3">
          <h2 className="card-title">Add FAQ / policy text</h2>
          <input className="input" placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <textarea className="input h-24" placeholder="Q&A or policy text…" value={text} onChange={(e) => setText(e.target.value)} />
          <button className="btn" disabled={busy || !title || !text} onClick={addText}>Add</button>
        </div>
      </div>
      <div className="card mb-6">
        <h2 className="card-title">Test retrieval</h2>
        <p className="card-desc mb-4">Search the knowledge base the way the agent does.</p>
        <div className="flex gap-2">
          <input className="input" placeholder="e.g. visiting hours" value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="btn-ghost" onClick={async () => setHits(await api(`/knowledge/search?q=${encodeURIComponent(q)}`))}>Search</button>
        </div>
        {hits && (hits.length ? hits.map((h, i) => (
          <div key={i} className="mt-3 rounded-2xl bg-slate-50 p-4 text-sm"><div className="text-xs font-medium text-slate-500">{h.title} · score {h.score}</div><div className="mt-1.5 whitespace-pre-wrap leading-relaxed text-slate-700">{h.content.slice(0, 400)}</div></div>
        )) : <div className="mt-3 text-sm text-slate-500">No matches</div>)}
      </div>
      <div className="card card-table">
        {docs?.length ? (
          <table className="table table-stack">
            <thead><tr><th>Title</th><th>Type</th><th>Status</th><th>Chunks</th><th>Added</th><th></th></tr></thead>
            <tbody>{docs.map((d) => (
              <tr key={d.id}>
                <td data-label="Title" className="font-medium text-slate-900">{d.title}{d.error && <div className="mt-1 text-sm font-normal text-rose-600">{d.error}</div>}</td>
                <td data-label="Type" className="uppercase text-slate-500">{d.source_type}</td><td data-label="Status"><Badge tone={statusTone(d.status)}>{d.status}</Badge></td><td data-label="Chunks" className="tabular-nums">{d.chunk_count}</td><td data-label="Added" className="whitespace-nowrap text-slate-500">{fmtDate(d.created_at)}</td>
                <td className="whitespace-nowrap text-right">
                  <span className="inline-flex gap-1.5"><button className="btn-ghost btn-sm" onClick={() => act(`/knowledge/documents/${d.id}/reindex`, 'POST')}>Reindex</button>
                  <button className="btn-ghost btn-sm text-rose-600" onClick={() => confirm(`Delete "${d.title}"?`) && act(`/knowledge/documents/${d.id}`, 'DELETE')}>Delete</button></span>
                </td>
              </tr>
            ))}</tbody>
          </table>
        ) : <div className="p-3"><Empty>No documents yet.</Empty></div>}
      </div>
    </div>
  )
}
