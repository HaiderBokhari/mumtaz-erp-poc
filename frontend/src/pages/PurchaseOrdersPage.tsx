import { useEffect, useState, type FormEvent } from 'react'
import api from '../api/client'
import type { Paginated, PurchaseOrder, SKU, Warehouse } from '../types'
import { formatMoney } from '../utils/format'

const STATUS_COLORS: Record<string, string> = {
  DRAFT: 'bg-slate-200 text-slate-600',
  PENDING_APPROVAL: 'bg-amber-100 text-amber-700',
  SUBMITTED_TO_PTC: 'bg-blue-100 text-blue-700',
  RECEIVED: 'bg-emerald-100 text-emerald-700',
  CANCELLED: 'bg-red-100 text-red-700',
}

interface DraftLine { sku: string; quantity: string; unit_cost: string }

export default function PurchaseOrdersPage() {
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [skus, setSkus] = useState<SKU[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [warehouse, setWarehouse] = useState('')
  const [ptcRef, setPtcRef] = useState('')
  const [lines, setLines] = useState<DraftLine[]>([{ sku: '', quantity: '', unit_cost: '' }])
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)

  async function loadOrders() {
    setLoading(true)
    try {
      const res = await api.get<Paginated<PurchaseOrder> | PurchaseOrder[]>('purchase-orders/', { params: { page_size: 100 } })
      setOrders(Array.isArray(res.data) ? res.data : res.data.results)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
    api.get<Paginated<Warehouse> | Warehouse[]>('warehouses/', { params: { page_size: 100 } })
      .then((res) => setWarehouses(Array.isArray(res.data) ? res.data : res.data.results))
    api.get<Paginated<SKU> | SKU[]>('skus/', { params: { page_size: 500, status: 'ACTIVE' } })
      .then((res) => setSkus(Array.isArray(res.data) ? res.data : res.data.results))
  }, [])

  function updateLine(index: number, patch: Partial<DraftLine>) {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)))
  }

  function addLine() {
    setLines((prev) => [...prev, { sku: '', quantity: '', unit_cost: '' }])
  }

  function removeLine(index: number) {
    setLines((prev) => prev.filter((_, i) => i !== index))
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      await api.post('purchase-orders/', {
        warehouse: Number(warehouse),
        ptc_reference_number: ptcRef,
        lines: lines
          .filter((l) => l.sku)
          .map((l) => ({ sku: Number(l.sku), quantity: l.quantity, unit_cost: l.unit_cost })),
      })
      setShowForm(false)
      setWarehouse('')
      setPtcRef('')
      setLines([{ sku: '', quantity: '', unit_cost: '' }])
      loadOrders()
    } catch (err: any) {
      setError(err?.response?.data ? JSON.stringify(err.response.data) : 'Could not create purchase order.')
    }
  }

  async function runAction(po: PurchaseOrder, action: 'submit' | 'approve' | 'receive') {
    setBusyId(po.id)
    try {
      await api.post(`purchase-orders/${po.id}/${action}/`)
      await loadOrders()
    } catch (err: any) {
      alert(err?.response?.data?.detail || `Could not ${action} the purchase order.`)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Purchase Orders</h1>
          <p className="text-sm text-slate-500">Aligned with orders placed on PTC's SAP portal.</p>
        </div>
        <button className="btn-primary" onClick={() => setShowForm((s) => !s)}>
          {showForm ? 'Cancel' : '+ New Purchase Order'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="card p-4 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <select className="input" value={warehouse} onChange={(e) => setWarehouse(e.target.value)} required>
              <option value="">Warehouse...</option>
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
            <input className="input" placeholder="PTC SAP reference number" value={ptcRef} onChange={(e) => setPtcRef(e.target.value)} />
          </div>

          <div className="space-y-2">
            {lines.map((line, i) => (
              <div key={i} className="grid grid-cols-[1fr_120px_120px_auto] gap-2 items-center">
                <select className="input" value={line.sku} onChange={(e) => updateLine(i, { sku: e.target.value })} required>
                  <option value="">SKU...</option>
                  {skus.map((s) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                </select>
                <input className="input" type="number" step="0.001" placeholder="Qty" value={line.quantity} onChange={(e) => updateLine(i, { quantity: e.target.value })} required />
                <input className="input" type="number" step="0.01" placeholder="Unit cost" value={line.unit_cost} onChange={(e) => updateLine(i, { unit_cost: e.target.value })} required />
                <button type="button" className="btn-secondary" onClick={() => removeLine(i)} disabled={lines.length === 1}>Remove</button>
              </div>
            ))}
            <button type="button" className="btn-secondary" onClick={addLine}>+ Add line</button>
          </div>

          <button type="submit" className="btn-primary">Save Purchase Order</button>
          {error && <div className="text-sm text-red-600">{error}</div>}
        </form>
      )}

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>PO #</th><th>PTC Ref</th><th>Warehouse</th><th>Status</th>
              <th className="text-right">Value</th><th>Order date</th><th></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="text-center text-slate-400 py-6">Loading...</td></tr>
            ) : orders.length === 0 ? (
              <tr><td colSpan={7} className="text-center text-slate-400 py-6">No purchase orders yet.</td></tr>
            ) : orders.map((po) => (
              <tr key={po.id}>
                <td className="font-mono text-xs">{po.po_number}</td>
                <td className="font-mono text-xs">{po.ptc_reference_number || '—'}</td>
                <td>{po.warehouse_name}</td>
                <td><span className={`badge ${STATUS_COLORS[po.status]}`}>{po.status.replace(/_/g, ' ')}</span></td>
                <td className="text-right">Rs {formatMoney(po.total_value)}</td>
                <td>{po.order_date}</td>
                <td className="text-right space-x-2 whitespace-nowrap">
                  {po.status === 'DRAFT' && (
                    <button className="btn-secondary" disabled={busyId === po.id} onClick={() => runAction(po, 'submit')}>Submit</button>
                  )}
                  {po.status === 'PENDING_APPROVAL' && (
                    <button className="btn-secondary" disabled={busyId === po.id} onClick={() => runAction(po, 'approve')}>Approve</button>
                  )}
                  {po.status === 'SUBMITTED_TO_PTC' && (
                    <button className="btn-secondary" disabled={busyId === po.id} onClick={() => runAction(po, 'receive')}>Receive</button>
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
