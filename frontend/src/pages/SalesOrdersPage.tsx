import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import api from '../api/client'
import type { Paginated, SalesOrder, SKU, Shop, Warehouse } from '../types'
import { formatMoney } from '../utils/format'

const STATUS_COLORS: Record<string, string> = {
  DRAFT: 'bg-slate-200 text-slate-600',
  CONFIRMED: 'bg-emerald-100 text-emerald-700',
  CANCELLED: 'bg-red-100 text-red-700',
}

interface DraftLine { sku: string; quantity: string; unit_price: string }
interface StockMovementRow {
  date: string
  warehouse_name: string
  out_quantity: string
  in_quantity: string
}

export default function SalesOrdersPage() {
  const [orders, setOrders] = useState<SalesOrder[]>([])
  const [shops, setShops] = useState<Shop[]>([])
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [skus, setSkus] = useState<SKU[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [shop, setShop] = useState('')
  const [warehouse, setWarehouse] = useState('')
  const [ptcRef, setPtcRef] = useState('')
  const [lines, setLines] = useState<DraftLine[]>([{ sku: '', quantity: '', unit_price: '' }])
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)
  const [uploadMsg, setUploadMsg] = useState('')
  const [shopFilter, setShopFilter] = useState('')
  const [showMovement, setShowMovement] = useState(false)
  const [movement, setMovement] = useState<StockMovementRow[]>([])

  async function loadOrders(shopId?: string) {
    setLoading(true)
    try {
      const res = await api.get<Paginated<SalesOrder> | SalesOrder[]>('sales-orders/', {
        params: { page_size: 100, ordering: '-timestamp', shop: shopId || undefined },
      })
      setOrders(Array.isArray(res.data) ? res.data : res.data.results)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
    api.get<Paginated<Shop> | Shop[]>('shops/', { params: { page_size: 200 } }).then((res) => setShops(Array.isArray(res.data) ? res.data : res.data.results))
    api.get<Paginated<Warehouse> | Warehouse[]>('warehouses/', { params: { page_size: 100 } }).then((res) => setWarehouses(Array.isArray(res.data) ? res.data : res.data.results))
    api.get<Paginated<SKU> | SKU[]>('skus/', { params: { page_size: 500, status: 'ACTIVE' } }).then((res) => setSkus(Array.isArray(res.data) ? res.data : res.data.results))
  }, [])

  async function toggleMovement() {
    if (!showMovement) {
      const res = await api.get<StockMovementRow[]>('sales-orders/stock_movement_summary/')
      setMovement(res.data)
    }
    setShowMovement((s) => !s)
  }

  function updateLine(index: number, patch: Partial<DraftLine>) {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)))
  }

  function addLine() {
    setLines((prev) => [...prev, { sku: '', quantity: '', unit_price: '' }])
  }

  function removeLine(index: number) {
    setLines((prev) => prev.filter((_, i) => i !== index))
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setError('')
    const selectedShop = shops.find((s) => s.id === Number(shop))
    if (!selectedShop) {
      setError('Please select a shop.')
      return
    }
    try {
      await api.post('sales-orders/', {
        shop: Number(shop),
        channel: selectedShop.channel,
        warehouse: Number(warehouse),
        ptc_reference_number: ptcRef,
        lines: lines
          .filter((l) => l.sku)
          .map((l) => ({ sku: Number(l.sku), quantity: l.quantity, unit_price: l.unit_price })),
      })
      setShowForm(false)
      setShop(''); setWarehouse(''); setPtcRef('')
      setLines([{ sku: '', quantity: '', unit_price: '' }])
      loadOrders()
    } catch (err: any) {
      setError(err?.response?.data ? JSON.stringify(err.response.data) : 'Could not create sales order.')
    }
  }

  async function confirmOrder(so: SalesOrder) {
    setBusyId(so.id)
    try {
      await api.post(`sales-orders/${so.id}/confirm/`)
      await loadOrders()
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Could not confirm the sales order.')
    } finally {
      setBusyId(null)
    }
  }

  async function handleUpload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadMsg('Uploading...')
    const data = new FormData()
    data.append('file', file)
    try {
      const res = await api.post('sales-orders/upload_ptc_sales/', data, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setUploadMsg(`${res.data.orders_created} order(s) created from ${res.data.rows_processed} row(s).${res.data.errors.length ? ` ${res.data.errors.length} error(s).` : ''}`)
      loadOrders()
    } catch {
      setUploadMsg('Upload failed.')
    } finally {
      e.target.value = ''
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold">Sales Orders</h1>
          <p className="text-sm text-slate-500">Manual entry, or bulk upload from PTC/BIZOM sales files.</p>
        </div>
        <div className="flex items-center gap-2 no-print">
          <a className="btn-secondary" href={`${api.defaults.baseURL}/sales-orders/upload_template/`} target="_blank" rel="noreferrer">
            Download upload template
          </a>
          <label className="btn-secondary cursor-pointer">
            Upload PTC sales file
            <input type="file" accept=".csv,.xlsx" className="hidden" onChange={handleUpload} />
          </label>
          <button className="btn-secondary" onClick={toggleMovement}>
            {showMovement ? 'Hide stock movement' : 'Distribution stock movement'}
          </button>
          <button className="btn-primary" onClick={() => setShowForm((s) => !s)}>
            {showForm ? 'Cancel' : '+ New Sales Order'}
          </button>
        </div>
      </div>
      {uploadMsg && <div className="text-sm text-slate-600 no-print">{uploadMsg}</div>}

      {showMovement && (
        <div className="card overflow-x-auto">
          <div className="flex items-center justify-between p-4 pb-0">
            <h2 className="font-medium">Daily distribution out/in stock summary</h2>
            <button className="btn-secondary no-print" onClick={() => window.print()}>Print</button>
          </div>
          <table className="data-table">
            <thead>
              <tr><th>Date</th><th>Warehouse</th><th className="text-right">Out (dispatched)</th><th className="text-right">In (returns)</th></tr>
            </thead>
            <tbody>
              {movement.length === 0 ? (
                <tr><td colSpan={4} className="text-center text-slate-400 py-6">No stock movement in range.</td></tr>
              ) : movement.map((row, i) => (
                <tr key={i}>
                  <td>{row.date}</td>
                  <td>{row.warehouse_name}</td>
                  <td className="text-right">{row.out_quantity}</td>
                  <td className="text-right">{row.in_quantity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <form onSubmit={handleCreate} className="card p-4 space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <select className="input" value={shop} onChange={(e) => setShop(e.target.value)} required>
              <option value="">Shop...</option>
              {shops.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.channel_name})</option>)}
            </select>
            <select className="input" value={warehouse} onChange={(e) => setWarehouse(e.target.value)} required>
              <option value="">Source warehouse...</option>
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
            <input className="input" placeholder="PTC reference number" value={ptcRef} onChange={(e) => setPtcRef(e.target.value)} />
          </div>

          <div className="space-y-2">
            {lines.map((line, i) => (
              <div key={i} className="grid grid-cols-[1fr_120px_120px_auto] gap-2 items-center">
                <select className="input" value={line.sku} onChange={(e) => updateLine(i, { sku: e.target.value })} required>
                  <option value="">SKU...</option>
                  {skus.map((s) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                </select>
                <input className="input" type="number" step="0.001" placeholder="Qty" value={line.quantity} onChange={(e) => updateLine(i, { quantity: e.target.value })} required />
                <input className="input" type="number" step="0.01" placeholder="Unit price" value={line.unit_price} onChange={(e) => updateLine(i, { unit_price: e.target.value })} required />
                <button type="button" className="btn-secondary" onClick={() => removeLine(i)} disabled={lines.length === 1}>Remove</button>
              </div>
            ))}
            <button type="button" className="btn-secondary" onClick={addLine}>+ Add line</button>
          </div>

          <button type="submit" className="btn-primary">Save Sales Order</button>
          {error && <div className="text-sm text-red-600">{error}</div>}
        </form>
      )}

      <div className="flex items-center justify-between no-print">
        <select
          className="input max-w-xs"
          value={shopFilter}
          onChange={(e) => { setShopFilter(e.target.value); loadOrders(e.target.value) }}
        >
          <option value="">All shops (retailers/wholesalers)</option>
          {shops.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.channel_name})</option>)}
        </select>
        <button className="btn-secondary" onClick={() => window.print()}>Print</button>
      </div>

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>SO #</th><th>Shop</th><th>Channel</th><th>DR</th><th>Status</th>
              <th className="text-right">Value</th><th>Date</th><th></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="text-center text-slate-400 py-6">Loading...</td></tr>
            ) : orders.length === 0 ? (
              <tr><td colSpan={8} className="text-center text-slate-400 py-6">No sales orders yet.</td></tr>
            ) : orders.map((so) => (
              <tr key={so.id}>
                <td className="font-mono text-xs">{so.so_number}</td>
                <td>{so.shop_name}</td>
                <td>{so.channel_name}</td>
                <td>{so.dr_name || '—'}</td>
                <td><span className={`badge ${STATUS_COLORS[so.status]}`}>{so.status}</span></td>
                <td className="text-right">Rs {formatMoney(so.total_value)}</td>
                <td>{so.order_date}</td>
                <td className="text-right">
                  {so.status === 'DRAFT' && (
                    <button className="btn-secondary" disabled={busyId === so.id} onClick={() => confirmOrder(so)}>Confirm</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
