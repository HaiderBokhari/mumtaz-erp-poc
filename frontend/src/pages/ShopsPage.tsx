import { useEffect, useState, type FormEvent } from 'react'
import api from '../api/client'
import type { Channel, Paginated, Shop } from '../types'
import { formatMoney } from '../utils/format'

export default function ShopsPage() {
  const [shops, setShops] = useState<Shop[]>([])
  const [channels, setChannels] = useState<Channel[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', channel: '', locality: '', address: '', contact_name: '', contact_phone: '', credit_limit: '0' })
  const [error, setError] = useState('')

  async function loadShops() {
    setLoading(true)
    try {
      const res = await api.get<Paginated<Shop> | Shop[]>('shops/', { params: { page_size: 200 } })
      setShops(Array.isArray(res.data) ? res.data : res.data.results)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadShops()
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
          <h1 className="text-xl font-semibold">Shops</h1>
          <p className="text-sm text-slate-500">Retailers, wholesalers and mandi traders &mdash; the buyer side of every sales order.</p>
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

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr><th>Name</th><th>Channel</th><th>Locality</th><th className="text-right">Credit limit</th><th className="text-right">Outstanding</th><th>Status</th></tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="text-center text-slate-400 py-6">Loading...</td></tr>
            ) : shops.length === 0 ? (
              <tr><td colSpan={6} className="text-center text-slate-400 py-6">No shops registered yet.</td></tr>
            ) : shops.map((shop) => (
              <tr key={shop.id}>
                <td>{shop.name}</td>
                <td>{shop.channel_name}</td>
                <td>{shop.locality}</td>
                <td className="text-right">Rs {formatMoney(shop.credit_limit)}</td>
                <td className="text-right">Rs {formatMoney(shop.outstanding_balance)}</td>
                <td>
                  <span className={`badge ${shop.status === 'ACTIVE' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'}`}>
                    {shop.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
