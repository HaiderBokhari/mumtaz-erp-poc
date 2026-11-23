import { useEffect, useMemo, useState } from 'react'
import api from '../api/client'
import { formatNumber } from '../utils/format'

type Bucket = 'RETAIL' | 'SCATTERED'
type Grid = Record<string, Record<Bucket, Record<string, string>>>

interface DayResponse {
  date: string
  columns: { key: string; label: string }[]
  drs: { id: number; code: string; name: string }[]
  values: Record<string, Partial<Record<Bucket, Record<string, string>>>>
  saved?: { rows_changed: number; drs_updated: number }
}

const BUCKET_LABELS: Record<Bucket, string> = {
  RETAIL: 'Sold in retail',
  SCATTERED: 'Sold in scattered wholesale',
}

const today = () => new Date().toISOString().slice(0, 10)
const num = (v: string | undefined) => Number(v || 0)

function toGrid(data: DayResponse): Grid {
  const grid: Grid = {}
  for (const dr of data.drs) {
    const saved = data.values[String(dr.id)] ?? {}
    grid[dr.id] = { RETAIL: {}, SCATTERED: {} }
    for (const bucket of ['RETAIL', 'SCATTERED'] as Bucket[]) {
      for (const [key, value] of Object.entries(saved[bucket] ?? {})) {
        grid[dr.id][bucket][key] = String(Number(value))
      }
    }
  }
  return grid
}

export default function SalesEntryPage() {
  const [date, setDate] = useState(today())
  const [bucket, setBucket] = useState<Bucket>('RETAIL')
  const [data, setData] = useState<DayResponse | null>(null)
  const [grid, setGrid] = useState<Grid>({})
  const [original, setOriginal] = useState<Grid>({})
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  function apply(res: DayResponse) {
    setData(res)
    const g = toGrid(res)
    setGrid(g)
    setOriginal(JSON.parse(JSON.stringify(g)))
  }

  useEffect(() => {
    setMessage('')
    setError('')
    api.get<DayResponse>('actual-sales/day/', { params: { date } }).then((res) => apply(res.data))
  }, [date])

  // Only send cells that changed, so a save never touches untouched rows.
  const changes = useMemo(() => {
    const out: Record<string, Partial<Record<Bucket, Record<string, string>>>> = {}
    for (const [drId, buckets] of Object.entries(grid)) {
      for (const b of ['RETAIL', 'SCATTERED'] as Bucket[]) {
        const keys = new Set([...Object.keys(buckets[b]), ...Object.keys(original[drId]?.[b] ?? {})])
        for (const key of keys) {
          if (num(buckets[b][key]) !== num(original[drId]?.[b]?.[key])) {
            out[drId] = out[drId] ?? {}
            out[drId][b] = { ...(out[drId][b] ?? {}), [key]: String(num(buckets[b][key])) }
          }
        }
      }
    }
    return out
  }, [grid, original])
  const changeCount = Object.values(changes).reduce(
    (n, buckets) => n + Object.values(buckets).reduce((m, cols) => m + Object.keys(cols ?? {}).length, 0), 0,
  )

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (changeCount) e.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [changeCount])

  function setCell(drId: number, key: string, value: string) {
    setGrid((g) => ({ ...g, [drId]: { ...g[drId], [bucket]: { ...g[drId][bucket], [key]: value } } }))
  }

  async function save() {
    setSaving(true)
    setMessage('')
    setError('')
    try {
      const res = await api.post<DayResponse>('actual-sales/day/', { date, values: changes })
      apply(res.data)
      setMessage(`Saved ${res.data.saved?.rows_changed ?? 0} change(s) for ${res.data.saved?.drs_updated ?? 0} DR(s). Stock and accounts updated.`)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Could not save.')
    } finally {
      setSaving(false)
    }
  }

  if (!data) return <div className="text-slate-500">Loading...</div>

  const columnTotals = Object.fromEntries(data.columns.map((c) => [
    c.key, data.drs.reduce((sum, dr) => sum + num(grid[dr.id]?.[bucket]?.[c.key]), 0),
  ]))
  const grandTotal = Object.values(columnTotals).reduce((a, b) => a + b, 0)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Daily Sales Entry</h1>
          <p className="text-sm text-slate-500 max-w-3xl">
            Your ACTUAL SALE sheet: one row per DR, quantities in M. Saving updates godown stock, the DR&rsquo;s
            account and commission straight away. You can come back and correct a day; only the difference is posted.
          </p>
        </div>
        <div className="flex items-center gap-2 no-print">
          <input type="date" className="input w-auto" value={date} onChange={(e) => setDate(e.target.value)} />
          <button className="btn-primary" disabled={!changeCount || saving} onClick={save}>
            {saving ? 'Saving...' : changeCount ? `Save ${changeCount} change${changeCount > 1 ? 's' : ''}` : 'Saved'}
          </button>
        </div>
      </div>

      {message && <div className="rounded-lg bg-emerald-50 text-emerald-800 text-sm px-3 py-2">{message}</div>}
      {error && <div className="rounded-lg bg-red-50 text-red-700 text-sm px-3 py-2">{error}</div>}

      <div className="flex gap-1 border-b border-slate-200 no-print">
        {(['RETAIL', 'SCATTERED'] as Bucket[]).map((b) => (
          <button
            key={b}
            onClick={() => setBucket(b)}
            className={`px-4 py-2 text-sm -mb-px border-b-2 ${
              bucket === b ? 'border-brand-500 text-brand-600 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            {BUCKET_LABELS[b]}
          </button>
        ))}
      </div>

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th className="sticky left-0 bg-white">DR</th>
              {data.columns.map((c) => <th key={c.key} className="text-right">{c.label}</th>)}
              <th className="text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            {data.drs.map((dr) => {
              const row = grid[dr.id]?.[bucket] ?? {}
              const rowTotal = data.columns.reduce((sum, c) => sum + num(row[c.key]), 0)
              return (
                <tr key={dr.id}>
                  <td className="sticky left-0 bg-white whitespace-nowrap">
                    <div className="font-medium">{dr.name}</div>
                    <div className="text-xs text-slate-400">{dr.code.replace('SGD_SGD_', '')}</div>
                  </td>
                  {data.columns.map((c) => {
                    const changed = num(row[c.key]) !== num(original[dr.id]?.[bucket]?.[c.key])
                    return (
                      <td key={c.key} className="px-1 py-1">
                        <input
                          type="number" step="0.01" inputMode="decimal"
                          className={`w-20 rounded border px-2 py-1 text-right text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${
                            changed ? 'border-amber-400 bg-amber-50' : 'border-slate-200'
                          }`}
                          value={row[c.key] ?? ''}
                          placeholder="0"
                          onChange={(e) => setCell(dr.id, c.key, e.target.value)}
                        />
                      </td>
                    )
                  })}
                  <td className="text-right font-medium">{formatNumber(rowTotal.toFixed(2))}</td>
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr className="font-semibold bg-slate-50">
              <td className="py-2 px-3 sticky left-0 bg-slate-50">Total</td>
              {data.columns.map((c) => (
                <td key={c.key} className="text-right px-3">{formatNumber(columnTotals[c.key].toFixed(2))}</td>
              ))}
              <td className="text-right px-3">{formatNumber(grandTotal.toFixed(2))}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        Column notes from your team: &ldquo;Velo Nano&rdquo; is the column headed B&amp;H on the sheet; &ldquo;CI&rdquo; includes
        Capstan Select; CbPMO includes the Q2 LEP pack. Changed cells are highlighted until saved.
      </p>
    </div>
  )
}
