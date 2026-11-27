import { Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { useApi } from '../hooks/useApi'
import { Badge, Empty, PageHeader, fmtDate, statusTone } from '../components/ui'

type Row = Record<string, any>

function Table({ rows, cols }: { rows: Row[] | null; cols: [string, string, ((r: Row) => React.ReactNode)?][] }) {
  if (!rows?.length) return <Empty>No records.</Empty>
  return (
    <div className="overflow-x-auto"><table className="table table-stack">
      <thead><tr>{cols.map(([, l]) => <th key={l}>{l}</th>)}</tr></thead>
      <tbody>{rows.map((r) => <tr key={r.id}>{cols.map(([k, l, f]) => <td key={l} data-label={l}>{f ? f(r) : String(r[k] ?? '—')}</td>)}</tr>)}</tbody>
    </table></div>
  )
}

const inr = (v: number) => (v >= 1e7 ? `₹${(v / 1e7).toFixed(2)} Cr` : `₹${(v / 1e5).toFixed(1)} L`)

export default function BusinessData() {
  const { tenants, tenantId } = useAuth()
  const industry = tenants.find((t) => t.id === tenantId)?.industry
  const props = useApi<Row[]>(industry === 'real_estate' ? '/data/properties' : null)
  const doctors = useApi<Row[]>(industry === 'healthcare' ? '/data/doctors' : null)
  const appts = useApi<Row[]>('/appointments')
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Records" title="Business Data" subtitle="Live records the agent reads and writes through its tools." />
      {industry === 'real_estate' && (
        <div className="card"><h2 className="card-title mb-3">Properties</h2>
          <Table rows={props.data} cols={[['name', 'Name'], ['locality', 'Locality'], ['city', 'City'], ['price', 'Price', (r) => `${inr(r.price_min)} – ${inr(r.price_max)}`],
            ['units_available', 'Units'], ['status', 'Status', (r) => <Badge tone={r.status === 'available' ? 'green' : 'gray'}>{r.status}</Badge>], ['possession', 'Possession']]} /></div>
      )}
      {industry === 'healthcare' && (
        <div className="card"><h2 className="card-title mb-3">Doctors</h2>
          <Table rows={doctors.data} cols={[['name', 'Name'], ['specialization', 'Specialization'], ['department', 'Department'], ['consultation_fee', 'Fee (₹)'], ['free_slots', 'Free slots']]} /></div>
      )}
      <div className="card"><h2 className="card-title mb-3">Appointments / site visits</h2>
        <Table rows={appts.data} cols={[['starts_at', 'When', (r) => fmtDate(r.starts_at)], ['kind', 'Type'], ['contact_name', 'Name'], ['contact_phone', 'Phone'], ['status', 'Status', (r) => <Badge tone={statusTone(r.status)}>{String(r.status).replace(/_/g, ' ')}</Badge>], ['notes', 'Notes']]} /></div>
      <div className="card flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="card-title">Leads</h2>
          <p className="card-desc">Assign, track and export leads on the Follow-ups page.</p></div>
        <Link to="/follow-ups" className="btn">Open Follow-ups</Link></div>
    </div>
  )
}
