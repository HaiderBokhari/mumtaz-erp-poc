import { useEffect, useState, type FormEvent } from 'react'
import api from '../api/client'
import type { Brand, Paginated, SKU } from '../types'
import { formatMoney } from '../utils/format'

export default function CatalogPage() {
  const [brands, setBrands] = useState<Brand[]>([])
  const [skus, setSkus] = useState<SKU[]>([])
  const [brandFilter, setBrandFilter] = useState<number | ''>('')
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ code: '', name: '', brand: '', variant: '', pack_size: '', sticks_per_pack: '20', current_cost_price: '' })
  const [error, setError] = useState('')

  async function loadBrands() {
    const res = await api.get<Paginated<Brand> | Brand[]>('brands/', { params: { page_size: 200 } })
    setBrands(Array.isArray(res.data) ? res.data : res.data.results)
  }

  async function loadSkus() {
    setLoading(true)
    try {
      const res = await api.get<Paginated<SKU> | SKU[]>('skus/', {
        params: { page_size: 200, brand: brandFilter || undefined },
      })
      setSkus(Array.isArray(res.data) ? res.data : res.data.results)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadBrands() }, [])
  useEffect(() => { loadSkus() }, [brandFilter])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      await api.post('skus/', {
        ...form,
        brand: Number(form.brand),
        sticks_per_pack: Number(form.sticks_per_pack),
        current_cost_price: form.current_cost_price || '0',
      })
      setShowForm(false)
      setForm({ code: '', name: '', brand: '', variant: '', pack_size: '', sticks_per_pack: '20', current_cost_price: '' })
      loadSkus()
    } catch (err: any) {
      setError(err?.response?.data ? JSON.stringify(err.response.data) : 'Could not create SKU.')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Brands &amp; SKUs</h1>
          <p className="text-sm text-slate-500">{brands.length} brands &middot; {skus.length} SKUs shown</p>
        </div>
        <button className="btn-primary" onClick={() => setShowForm((s) => !s)}>
          {showForm ? 'Cancel' : '+ New SKU'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="card p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          <input className="input" placeholder="SKU code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required />
          <input className="input" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          <select className="input" value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} required>
            <option value="">Brand...</option>
            {brands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
          <input className="input" placeholder="Variant" value={form.variant} onChange={(e) => setForm({ ...form, variant: e.target.value })} />
          <input className="input" placeholder="Pack size (e.g. 20 HL)" value={form.pack_size} onChange={(e) => setForm({ ...form, pack_size: e.target.value })} required />
          <input className="input" type="number" placeholder="Sticks per pack" value={form.sticks_per_pack} onChange={(e) => setForm({ ...form, sticks_per_pack: e.target.value })} />
          <input className="input" type="number" step="0.01" placeholder="Cost price" value={form.current_cost_price} onChange={(e) => setForm({ ...form, current_cost_price: e.target.value })} />
          <button type="submit" className="btn-primary">Save SKU</button>
          {error && <div className="col-span-full text-sm text-red-600">{error}</div>}
        </form>
      )}

      <div className="flex items-center gap-3">
        <select className="input max-w-xs" value={brandFilter} onChange={(e) => setBrandFilter(e.target.value ? Number(e.target.value) : '')}>
          <option value="">All brands</option>
          {brands.map((b) => <option key={b.id} value={b.id}>{b.name} ({b.sku_count})</option>)}
        </select>
      </div>

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Code</th><th>Name</th><th>Brand</th><th>Pack</th><th>Sticks/pack</th><th>Cost price</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="text-center text-slate-400 py-6">Loading...</td></tr>
            ) : skus.length === 0 ? (
              <tr><td colSpan={7} className="text-center text-slate-400 py-6">No SKUs found.</td></tr>
            ) : skus.map((sku) => (
              <tr key={sku.id}>
                <td className="font-mono text-xs">{sku.code}</td>
                <td>{sku.name}</td>
                <td>{sku.brand_name}</td>
                <td>{sku.pack_size}</td>
                <td>{sku.sticks_per_pack}</td>
                <td>Rs {formatMoney(sku.current_cost_price)}</td>
                <td>
                  <span className={`badge ${sku.status === 'ACTIVE' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'}`}>
                    {sku.status}
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
