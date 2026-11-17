import { useEffect, useState, type FormEvent } from 'react'
import api from '../api/client'
import type { Channel, Paginated, Shop } from '../types'
import { formatMoney } from '../utils/format'

export default function ShopsPage() {
  const [shops, setShops] = useState<Shop[]>([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [channelType, setChannelType] = useState('')
  const [channels, setChannels] = useState<Channel[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', channel: '', locality: '', address: '', contact_name: '', contact_phone: '', credit_limit: '0' })
  const [error, setError] = useState('')
  const PAGE_SIZE = 50

  async function loadShops() {
    setLoading(true)
    try {
      const params: Record<string, string | number> = { page, page_size: PAGE_SIZE }
      if (search) params.search = search
      if (channelType) params.channel__channel_type = channelType
      const res = await api.get<Paginated<Shop> | Shop[]>('shops/', { params })
      if (Array.isArray(res.data)) {
        setShops(res.data)
        setCount(res.data.length)
      } else {
        setShops(res.data.results)
        setCount(res.data.count)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const timer = setTimeout(loadShops, 250)
    return () => clearTimeout(timer)
  }, [page, search, channelType])

  useEffect(() => {
    api.get<Paginated<Channel> | Channel[]>('channels/', { params: { page_size: 100 } })
      .then((res) => setChannels(Array.isArray(res.data) ? res.data : res.data.results))
  }, [])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      await api.post('shops/', { ...form, channel: Number(form.channel) })
      setShowForm(false)
      setForm({ name: '', channel: '', locality: '', address: '', contact_name: '', contact_phone: '', credit_limit: '0' })
      loadShops()
    } catch (err: any) {
      setError(err?.response?.data ? JSON.stringify(err.response.data) : 'Could not create shop.')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Outlets</h1>
          <p className="text-sm text-slate-500">
            {formatMoney(count)} outlets from BIZOM, each on a DR&rsquo;s beat. Channel comes from BIZOM&rsquo;s
            retail/wholesale and urban/rural/mandi fields; filer status from the outlet&rsquo;s price list.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setShowForm((s) => !s)}>
          {showForm ? 'Cancel' : '+ New Shop'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="card p-4 grid grid-cols-2 md:grid-cols-3 gap-3">
          <input className="input" placeholder="Shop name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          <select className="input" value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })} required>
            <option value="">Channel...</option>
            {channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <input className="input" placeholder="Locality" value={form.locality} onChange={(e) => setForm({ ...form, locality: e.target.value })} />
          <input className="input" placeholder="Address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          <input className="input" placeholder="Contact name" value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} />
          <input className="input" placeholder="Contact phone" value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} />
          <input className="input" type="number" placeholder="Credit limit" value={form.credit_limit} onChange={(e) => setForm({ ...form, credit_limit: e.target.value })} />
          <button type="submit" className="btn-primary">Save Shop</button>
          {error && <div className="col-span-full text-sm text-red-600">{error}</div>}
        </form>
      )}

      <div className="flex flex-wrap gap-2">
        <input
          className="input w-72" placeholder="Search name, address, BIZOM ID or beat..."
          value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }}
        />
        <select className="input w-auto" value={channelType} onChange={(e) => { setChannelType(e.target.value); setPage(1) }}>
          <option value="">All channels</option>
          <option value="DD">DD &mdash; urban retail</option>
          <option value="VDD">VDD &mdash; rural retail</option>
          <option value="WS">UWS &mdash; urban wholesale</option>
          <option value="VWS">RWS &mdash; rural wholesale</option>
          <option value="MANDI">Mandi</option>
        </select>
      </div>

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr><th>Outlet</th><th>DR</th><th>Channel</th><th>Area</th><th>Visit days</th><th>Filer</th><th className="text-right">Outstanding</th></tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="text-center text-slate-400 py-6">Loading...</td></tr>
            ) : shops.length === 0 ? (
              <tr><td colSpan={7} className="text-center text-slate-400 py-6">No outlets match.</td></tr>
            ) : shops.map((shop) => (
              <tr key={shop.id}>
                <td>
                  <div className="font-medium">{shop.name}</div>
                  <div className="text-xs text-slate-400">
                    {shop.bizom_outlet_id ? `BIZOM ${shop.bizom_outlet_id} · ` : ''}{shop.address}
                  </div>
                </td>
                <td>{shop.dr_name || '—'}</td>
                <td>{shop.channel_name}</td>
                <td>{shop.area_type || shop.locality}</td>
                <td className="text-xs">{shop.visit_days?.replace(/;/g, ', ') || '—'}</td>
                <td>
                  <span className={`badge ${shop.filer_status === 'FILER' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                    {shop.filer_status === 'FILER' ? 'Filer' : 'Non-filer'}
                  </span>
                </td>
                <td className="text-right">Rs {formatMoney(shop.outstanding_balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex items-center justify-between px-3 py-2 text-sm text-slate-500">
          <span>Page {page} of {Math.max(1, Math.ceil(count / PAGE_SIZE))}</span>
          <div className="flex gap-2">
            <button className="btn-secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
            <button className="btn-secondary" disabled={page * PAGE_SIZE >= count} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        </div>
      </div>
    </div>
  )
}
