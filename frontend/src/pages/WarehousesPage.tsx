import { useEffect, useState } from 'react'
import api from '../api/client'
import type { Paginated, StockLevel, Warehouse } from '../types'
import { formatNumber } from '../utils/format'

export default function WarehousesPage() {
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [stockLevels, setStockLevels] = useState<StockLevel[]>([])
  const [warehouseFilter, setWarehouseFilter] = useState<number | ''>('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get<Paginated<Warehouse> | Warehouse[]>('warehouses/', { params: { page_size: 100 } }).then((res) => {
      setWarehouses(Array.isArray(res.data) ? res.data : res.data.results)
    })
  }, [])

  useEffect(() => {
    setLoading(true)
    api
      .get<Paginated<StockLevel> | StockLevel[]>('stock-levels/', {
        params: { page_size: 500, warehouse: warehouseFilter || undefined, search: search || undefined },
      })
      .then((res) => setStockLevels(Array.isArray(res.data) ? res.data : res.data.results))
      .finally(() => setLoading(false))
  }, [warehouseFilter, search])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Warehouses &amp; Stock</h1>
        <p className="text-sm text-slate-500">Stock-on-hand report, filterable by warehouse, SKU or brand.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {warehouses.map((wh) => (
          <div key={wh.id} className="card p-4">
            <div className="font-medium">{wh.name}</div>
            <div className="text-xs text-slate-500">{wh.location}</div>
            <div className="mt-2 flex gap-2 text-xs">
              {wh.is_head_office && <span className="badge bg-brand-100 text-brand-700">HQ</span>}
              {wh.requires_po_approval && <span className="badge bg-amber-100 text-amber-700">PO approval required</span>}
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select className="input max-w-xs" value={warehouseFilter} onChange={(e) => setWarehouseFilter(e.target.value ? Number(e.target.value) : '')}>
          <option value="">All warehouses</option>
          {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
        <input className="input max-w-xs" placeholder="Search SKU code/name..." value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr><th>Warehouse</th><th>SKU</th><th>Brand</th><th className="text-right">Quantity on hand</th></tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={4} className="text-center text-slate-400 py-6">Loading...</td></tr>
            ) : stockLevels.length === 0 ? (
              <tr><td colSpan={4} className="text-center text-slate-400 py-6">No stock records found.</td></tr>
            ) : stockLevels.map((s) => (
              <tr key={s.id}>
                <td>{s.warehouse_name}</td>
                <td>{s.sku_code} &mdash; {s.sku_name}</td>
                <td>{s.brand_name}</td>
                <td className="text-right font-medium">{formatNumber(s.quantity)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
