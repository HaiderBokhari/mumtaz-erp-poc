import { Fragment, useEffect, useMemo, useState } from 'react'
import api from '../api/client'
import { formatMoney, formatNumber } from '../utils/format'

type Bucket = 'RETAIL' | 'SCATTERED'
type Mode = 'ISSUANCE' | Bucket
type Section = 'FMC' | 'NC'
type Dash = Record<string, string>
type Grid = Record<string, Record<Bucket, Record<string, string>>>
type Side = 'issued' | 'returned'
type IssGrid = Record<string, Record<string, Record<Side, string>>>

interface Column { key: string; label: string; section: Section; group: string }
interface DR { id: number; code: string; name: string; channel: string }

interface DayResponse {
  date: string
  columns: Column[]
  prices: Record<string, Record<string, string>>   // channel type -> column -> Rs per M
  channels: { key: string; label: string }[]
  drs: DR[]
  values: Record<string, Partial<Record<Bucket, Record<string, string>>>>
  issuance: Record<string, Record<string, [string, string]>>
  dashboard: Record<string, string>
  saved?: { rows_changed: number; drs_updated: number }
}

const MODE_LABELS: Record<Mode, string> = {
  ISSUANCE: 'Issuance & Return',
  RETAIL: 'Sold in retail',
  SCATTERED: 'Sold in scattered wholesale',
}
const CHANNEL_SHORT: Record<string, string> = { DD: 'DD', VDD: 'VDD', WS: 'UWS', VWS: 'RWS', MANDI: 'Mandi', SHOP: 'Shop sale' }
const BUCKETS: Bucket[] = ['RETAIL', 'SCATTERED']
const SIDES: Side[] = ['issued', 'returned']

const today = () => new Date().toISOString().slice(0, 10)
const num = (v: string | undefined) => Number(v || 0)
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v))

/** What a DR's sale counts as: their own channel, or UWS/RWS for scattered wholesale by a DD/VDD DR. */
function saleChannel(dr: DR, bucket: Bucket) {
  if (bucket === 'SCATTERED') return ({ DD: 'WS', VDD: 'VWS' } as Record<string, string>)[dr.channel] ?? dr.channel
  return dr.channel
}

function toGrid(data: DayResponse): Grid {
  const grid: Grid = {}
  for (const dr of data.drs) {
    const saved = data.values[String(dr.id)] ?? {}
    grid[dr.id] = { RETAIL: {}, SCATTERED: {} }
    for (const bucket of BUCKETS) {
      for (const [key, value] of Object.entries(saved[bucket] ?? {})) {
        grid[dr.id][bucket][key] = String(Number(value))
      }
    }
  }
  return grid
}

function toIssGrid(data: DayResponse): IssGrid {
  const grid: IssGrid = {}
  for (const dr of data.drs) {
    grid[dr.id] = {}
    for (const c of data.columns) {
      const [issued, returned] = data.issuance[String(dr.id)]?.[c.key] ?? ['', '']
      grid[dr.id][c.key] = {
        issued: issued === '' ? '' : String(Number(issued)),
        returned: returned === '' ? '' : String(Number(returned)),
      }
    }
  }
  return grid
}

const cellClass = (changed: boolean) =>
  `w-20 rounded border px-2 py-1 text-right text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${
    changed ? 'border-amber-400 bg-amber-50' : 'border-slate-200'
  }`

export default function SalesEntryPage() {
  const [date, setDate] = useState(today())
  const [mode, setMode] = useState<Mode>('ISSUANCE')
  const [data, setData] = useState<DayResponse | null>(null)
  const [grid, setGrid] = useState<Grid>({})
  const [original, setOriginal] = useState<Grid>({})
  const [iss, setIss] = useState<IssGrid>({})
  const [issOriginal, setIssOriginal] = useState<IssGrid>({})
  const [dash, setDash] = useState<Dash>({})
  const [dashOriginal, setDashOriginal] = useState<Dash>({})
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  function apply(res: DayResponse) {
    setData(res)
    const g = toGrid(res)
    setGrid(g)
    setOriginal(clone(g))
    const i = toIssGrid(res)
    setIss(i)
    setIssOriginal(clone(i))
    const d: Dash = Object.fromEntries(Object.entries(res.dashboard ?? {}).map(([k, v]) => [k, String(Number(v))]))
    setDash(d)
    setDashOriginal(clone(d))
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
      for (const b of BUCKETS) {
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

  const issChanges = useMemo(() => {
    const out: Record<string, Record<string, Partial<Record<Side, string>>>> = {}
    for (const [drId, cols] of Object.entries(iss)) {
      for (const [key, sides] of Object.entries(cols)) {
        for (const side of SIDES) {
          if (num(sides[side]) !== num(issOriginal[drId]?.[key]?.[side])) {
            out[drId] = out[drId] ?? {}
            out[drId][key] = { ...(out[drId][key] ?? {}), [side]: String(num(sides[side])) }
          }
        }
      }
    }
    return out
  }, [iss, issOriginal])

  const count = (o: object) =>
    Object.values(o).reduce((n: number, inner: object) => n + Object.values(inner).reduce((m: number, x: object) => m + Object.keys(x ?? {}).length, 0), 0)
  const dashChanges = useMemo(() => {
    const out: Dash = {}
    for (const id of new Set([...Object.keys(dash), ...Object.keys(dashOriginal)])) {
      if ((dash[id] ?? '') !== (dashOriginal[id] ?? '') && num(dash[id]) !== num(dashOriginal[id])) out[id] = dash[id] ?? ''
    }
    return out
  }, [dash, dashOriginal])
  const changeCount = count(changes) + count(issChanges) + Object.keys(dashChanges).length

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (changeCount) e.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [changeCount])

  function setCell(drId: number, bucket: Bucket, key: string, value: string) {
    setGrid((g) => ({ ...g, [drId]: { ...g[drId], [bucket]: { ...g[drId][bucket], [key]: value } } }))
  }

  function setIssCell(drId: number, key: string, side: Side, value: string) {
    setIss((g) => ({ ...g, [drId]: { ...g[drId], [key]: { ...g[drId][key], [side]: value } } }))
  }

  async function save() {
    setSaving(true)
    setMessage('')
    setError('')
    try {
      let res: DayResponse | null = null
      let rows = 0
      const drs = new Set<string>()
      if (Object.keys(issChanges).length) {
        res = (await api.post<DayResponse>('actual-sales/day/', { date, issuance: issChanges })).data
        rows += res.saved?.rows_changed ?? 0
        Object.keys(issChanges).forEach((d) => drs.add(d))
      }
      if (Object.keys(dashChanges).length) {
        res = (await api.post<DayResponse>('actual-sales/day/', { date, dashboard: dashChanges })).data
        Object.keys(dashChanges).forEach((d) => drs.add(d))
      }
      if (Object.keys(changes).length) {
        res = (await api.post<DayResponse>('actual-sales/day/', { date, values: changes })).data
        rows += res.saved?.rows_changed ?? 0
        Object.keys(changes).forEach((d) => drs.add(d))
      }
      if (res) apply(res)
      setMessage(`Saved for ${drs.size} DR(s): ${rows} sale line(s) changed. Stock, the DR's account and commission are updated.`)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Could not save.')
    } finally {
      setSaving(false)
    }
  }

  // Channel-wise sale for the day, including edits not saved yet. A DR's
  // retail sale comes from issuance - return where that was entered.
  const byChannel = useMemo(() => {
    const out: Record<string, { m: number; rs: number }> = {}
    if (!data) return out
    for (const dr of data.drs) {
      for (const c of data.columns) {
        const sides = iss[dr.id]?.[c.key]
        const fromIssuance = sides && (num(sides.issued) || num(sides.returned) || num(issOriginal[dr.id]?.[c.key]?.issued))
        const retail = fromIssuance ? num(sides.issued) - num(sides.returned) : num(grid[dr.id]?.RETAIL?.[c.key])
        for (const [bucket, m] of [['RETAIL', retail], ['SCATTERED', num(grid[dr.id]?.SCATTERED?.[c.key])]] as [Bucket, number][]) {
          if (!m) continue
          const ch = saleChannel(dr, bucket)
          out[ch] = out[ch] ?? { m: 0, rs: 0 }
          out[ch].m += m
          out[ch].rs += m * num(data.prices[ch]?.[c.key])
        }
      }
    }
    return out
  }, [data, grid, iss, issOriginal])

  // Each DR's whole-day amount (retail + scattered, all brands), to compare with the BIZOM dashboard.
  const dayAmount = useMemo(() => {
    const out: Record<string, number> = {}
    if (!data) return out
    for (const dr of data.drs) {
      let rs = 0
      for (const c of data.columns) {
        const sides = iss[dr.id]?.[c.key]
        const fromIssuance = sides && (num(sides.issued) || num(sides.returned) || num(issOriginal[dr.id]?.[c.key]?.issued))
        const retail = fromIssuance ? num(sides.issued) - num(sides.returned) : num(grid[dr.id]?.RETAIL?.[c.key])
        rs += retail * num(data.prices[saleChannel(dr, 'RETAIL')]?.[c.key])
        rs += num(grid[dr.id]?.SCATTERED?.[c.key]) * num(data.prices[saleChannel(dr, 'SCATTERED')]?.[c.key])
      }
      out[dr.id] = rs
    }
    return out
  }, [data, grid, iss, issOriginal])

  if (!data) return <div className="text-slate-500">Loading...</div>

  const cols = data.columns
  const price = (dr: DR, bucket: Bucket, key: string) => num(data.prices[saleChannel(dr, bucket)]?.[key])
  const dayTotal = Object.values(byChannel).reduce((a, v) => ({ m: a.m + v.m, rs: a.rs + v.rs }), { m: 0, rs: 0 })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Daily Sales Entry</h1>
          <p className="text-sm text-slate-500 max-w-3xl">
            Enter each DR&rsquo;s morning issuance and evening return by brand, in M. Sale = issued &minus; returned, and the
            amount uses the BIZOM price list for that DR&rsquo;s channel. Saving updates godown stock, the DR&rsquo;s account
            and commission straight away. You can come back and correct a day; only the difference is posted.
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

      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
        {data.channels.map((ch) => (
          <div key={ch.key} className="card px-3 py-2">
            <div className="text-xs text-slate-500">{ch.label}</div>
            <div className="font-semibold">{formatNumber((byChannel[ch.key]?.m ?? 0).toFixed(2))} M</div>
            <div className="text-xs text-slate-500">Rs {formatMoney(byChannel[ch.key]?.rs ?? 0)}</div>
          </div>
        ))}
        <div className="card px-3 py-2 bg-slate-50">
          <div className="text-xs text-slate-500">Day total</div>
          <div className="font-semibold">{formatNumber(dayTotal.m.toFixed(2))} M</div>
          <div className="text-xs text-slate-500">Rs {formatMoney(dayTotal.rs)}</div>
        </div>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-2 border-b border-slate-200 no-print">
        <div className="flex gap-1">
          {(['ISSUANCE', ...BUCKETS] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-4 py-2 text-sm -mb-px border-b-2 ${
                mode === m ? 'border-brand-500 text-brand-600 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              {MODE_LABELS[m]}
            </button>
          ))}
        </div>
      </div>

      {mode === 'ISSUANCE' ? (
        <IssuanceTable
          data={data} cols={cols} iss={iss} original={issOriginal} price={price} onChange={setIssCell}
          dash={dash} dashOriginal={dashOriginal} dayAmount={dayAmount}
          onDash={(drId, v) => setDash((d) => ({ ...d, [drId]: v }))}
        />
      ) : (
        <BucketTable
          data={data} cols={cols} bucket={mode} grid={grid} original={original} price={price}
          onChange={(drId, key, value) => setCell(drId, mode, key, value)}
        />
      )}

      <p className="text-xs text-slate-500">
        Cigarettes and every Velo SKU are on one sheet; scroll right for Velo. &ldquo;BIZOM dashboard&rdquo;: type the
        DR&rsquo;s day value from the BIZOM dashboard; FBR is that minus the DR&rsquo;s whole-day amount here. Issuance &amp; Return saves the sale as the DR&rsquo;s retail sale, so it also shows on the &ldquo;Sold in
        retail&rdquo; tab. Channels: each DR&rsquo;s retail sale counts for their own channel (DD, VDD, Mandi device, Shop sale
        device for RTFs); scattered wholesale by a DD DR is UWS and by a VDD DR is RWS. CbPMO includes the Q2 LEP pack. Changed cells are highlighted until saved.
      </p>
    </div>
  )
}

function GroupHeader({ cols, lead, trail }: { cols: Column[]; lead: number; trail: number }) {
  if (!cols.some((c) => c.group)) return null
  const groups: { label: string; span: number }[] = []
  for (const c of cols) {
    const last = groups[groups.length - 1]
    if (last && last.label === c.group) last.span += 1
    else groups.push({ label: c.group, span: 1 })
  }
  return (
    <tr>
      <th colSpan={lead} className="sticky left-0 z-10 bg-white" />
      {groups.map((g, i) => (
        <th key={i} colSpan={g.span} className="text-center border-l border-slate-200 bg-slate-50">{g.label}</th>
      ))}
      <th colSpan={trail} />
    </tr>
  )
}

function DRCell({ dr }: { dr: DR }) {
  return (
    <>
      <div className="font-medium">{dr.name}</div>
      <div className="text-xs text-slate-400">{dr.code.replace('SGD_SGD_', '')} · {CHANNEL_SHORT[dr.channel] ?? dr.channel}</div>
    </>
  )
}

function IssuanceTable({ data, cols, iss, original, price, onChange, dash, dashOriginal, dayAmount, onDash }: {
  data: DayResponse
  cols: Column[]
  iss: IssGrid
  original: IssGrid
  price: (dr: DR, bucket: Bucket, key: string) => number
  onChange: (drId: number, key: string, side: Side, value: string) => void
  dash: Dash
  dashOriginal: Dash
  dayAmount: Record<string, number>
  onDash: (drId: number, value: string) => void
}) {
  let dashTotal = 0
  let fbrTotal = 0
  for (const dr of data.drs) {
    if (dash[dr.id]) {
      dashTotal += num(dash[dr.id])
      fbrTotal += num(dash[dr.id]) - (dayAmount[dr.id] ?? 0)
    }
  }
  const sale = (drId: number, key: string) => num(iss[drId]?.[key]?.issued) - num(iss[drId]?.[key]?.returned)
  const totals = { issued: 0, returned: 0, sale: 0, amount: 0 }
  const colSale: Record<string, number> = {}
  for (const dr of data.drs) {
    for (const c of cols) {
      totals.issued += num(iss[dr.id]?.[c.key]?.issued)
      totals.returned += num(iss[dr.id]?.[c.key]?.returned)
      const s = sale(dr.id, c.key)
      colSale[c.key] = (colSale[c.key] ?? 0) + s
      totals.sale += s
      totals.amount += s * price(dr, 'RETAIL', c.key)
    }
  }
  return (
    <div className="card overflow-x-auto">
      <table className="data-table">
        <thead>
          <GroupHeader cols={cols} lead={1} trail={4} />
          <tr>
            <th className="sticky left-0 z-10 bg-white">DR</th>
            {cols.map((c) => <th key={c.key} className="text-right">{c.label}</th>)}
            <th className="text-right">Total M</th>
            <th className="text-right">Amount Rs</th>
            <th className="text-right">BIZOM dashboard Rs</th>
            <th className="text-right">FBR Rs</th>
          </tr>
          <tr className="text-xs text-slate-400">
            <th className="sticky left-0 z-10 bg-white font-normal">BIZOM DD rate per M</th>
            {cols.map((c) => <th key={c.key} className="text-right font-normal">{formatNumber(num(data.prices.DD?.[c.key]).toFixed(0))}</th>)}
            <th /><th /><th /><th />
          </tr>
        </thead>
        <tbody>
          {data.drs.map((dr) => {
            const rowTotal = (side: Side) => cols.reduce((s, c) => s + num(iss[dr.id]?.[c.key]?.[side]), 0)
            const saleTotal = cols.reduce((s, c) => s + sale(dr.id, c.key), 0)
            const amount = cols.reduce((s, c) => s + sale(dr.id, c.key) * price(dr, 'RETAIL', c.key), 0)
            return (
              <Fragment key={dr.id}>
                {SIDES.map((side, i) => (
                  <tr key={side} className={i === 0 ? 'border-t-2 border-slate-200' : ''}>
                    <td className="sticky left-0 z-10 bg-white whitespace-nowrap py-0.5">
                      <div className="flex items-baseline justify-between gap-4">
                        <span>
                          {i === 0 && <span className="font-medium">{dr.name}</span>}
                          {i === 1 && (
                            <span className="text-xs text-slate-400">
                              {dr.code.replace('SGD_SGD_', '')} · {CHANNEL_SHORT[dr.channel] ?? dr.channel}
                            </span>
                          )}
                        </span>
                        <span className="text-xs text-slate-500">{side === 'issued' ? 'Issued' : 'Returned'}</span>
                      </div>
                    </td>
                    {cols.map((c) => {
                      const value = iss[dr.id]?.[c.key]?.[side] ?? ''
                      const changed = num(value) !== num(original[dr.id]?.[c.key]?.[side])
                      return (
                        <td key={c.key} className="px-1 py-0.5">
                          <input
                            type="number" step="0.01" min="0" inputMode="decimal"
                            className={cellClass(changed)} value={value} placeholder="0"
                            onChange={(e) => onChange(dr.id, c.key, side, e.target.value)}
                          />
                        </td>
                      )
                    })}
                    <td className="text-right text-slate-500">{formatNumber(rowTotal(side).toFixed(2))}</td>
                    <td />
                    <td />
                    <td />
                  </tr>
                ))}
                <tr className="bg-slate-50">
                  <td className="sticky left-0 z-10 bg-slate-50 text-right text-xs font-medium text-slate-700">Sale</td>
                  {cols.map((c) => {
                    const s = sale(dr.id, c.key)
                    return (
                      <td key={c.key} className={`text-right text-sm font-medium ${s < 0 ? 'text-red-600' : ''}`}>
                        {s ? formatNumber(s.toFixed(2)) : ''}
                      </td>
                    )
                  })}
                  <td className={`text-right font-semibold ${saleTotal < 0 ? 'text-red-600' : ''}`}>{formatNumber(saleTotal.toFixed(2))}</td>
                  <td className="text-right font-semibold">{formatMoney(amount)}</td>
                  <td className="px-1 py-0.5">
                    <input
                      type="number" step="1" min="0" inputMode="decimal" placeholder="—"
                      className={`${cellClass(num(dash[dr.id]) !== num(dashOriginal[dr.id]))} w-28`}
                      value={dash[dr.id] ?? ''} onChange={(e) => onDash(dr.id, e.target.value)}
                    />
                  </td>
                  <td className="text-right font-medium text-slate-700">
                    {dash[dr.id] ? formatMoney(num(dash[dr.id]) - (dayAmount[dr.id] ?? 0)) : ''}
                  </td>
                </tr>
              </Fragment>
            )
          })}
        </tbody>
        <tfoot>
          <tr className="font-semibold bg-slate-100 border-t-2 border-slate-300">
            <td className="py-2 px-3 sticky left-0 z-10 bg-slate-100 whitespace-nowrap">
              Total sale
              <div className="text-xs font-normal text-slate-500">
                {formatNumber(totals.issued.toFixed(2))} issued &minus; {formatNumber(totals.returned.toFixed(2))} returned
              </div>
            </td>
            {cols.map((c) => (
              <td key={c.key} className="text-right px-3">{formatNumber((colSale[c.key] ?? 0).toFixed(2))}</td>
            ))}
            <td className="text-right px-3">{formatNumber(totals.sale.toFixed(2))}</td>
            <td className="text-right px-3">{formatMoney(totals.amount)}</td>
            <td className="text-right px-3">{dashTotal ? formatMoney(dashTotal) : ''}</td>
            <td className="text-right px-3">{dashTotal ? formatMoney(fbrTotal) : ''}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function BucketTable({ data, cols, bucket, grid, original, price, onChange }: {
  data: DayResponse
  cols: Column[]
  bucket: Bucket
  grid: Grid
  original: Grid
  price: (dr: DR, bucket: Bucket, key: string) => number
  onChange: (drId: number, key: string, value: string) => void
}) {
  const columnTotals = Object.fromEntries(cols.map((c) => [
    c.key, data.drs.reduce((sum, dr) => sum + num(grid[dr.id]?.[bucket]?.[c.key]), 0),
  ]))
  const grandTotal = Object.values(columnTotals).reduce((a, b) => a + b, 0)
  const grandAmount = data.drs.reduce(
    (s, dr) => s + cols.reduce((t, c) => t + num(grid[dr.id]?.[bucket]?.[c.key]) * price(dr, bucket, c.key), 0), 0)
  return (
    <div className="card overflow-x-auto">
      <table className="data-table">
        <thead>
          <GroupHeader cols={cols} lead={1} trail={2} />
          <tr>
            <th className="sticky left-0 z-10 bg-white">DR</th>
            {cols.map((c) => <th key={c.key} className="text-right">{c.label}</th>)}
            <th className="text-right">Total M</th>
            <th className="text-right">Amount Rs</th>
          </tr>
        </thead>
        <tbody>
          {data.drs.map((dr) => {
            const row = grid[dr.id]?.[bucket] ?? {}
            const rowTotal = cols.reduce((sum, c) => sum + num(row[c.key]), 0)
            const amount = cols.reduce((sum, c) => sum + num(row[c.key]) * price(dr, bucket, c.key), 0)
            return (
              <tr key={dr.id}>
                <td className="sticky left-0 z-10 bg-white whitespace-nowrap"><DRCell dr={dr} /></td>
                {cols.map((c) => {
                  const changed = num(row[c.key]) !== num(original[dr.id]?.[bucket]?.[c.key])
                  return (
                    <td key={c.key} className="px-1 py-1">
                      <input
                        type="number" step="0.01" inputMode="decimal"
                        className={cellClass(changed)} value={row[c.key] ?? ''} placeholder="0"
                        onChange={(e) => onChange(dr.id, c.key, e.target.value)}
                      />
                    </td>
                  )
                })}
                <td className="text-right font-medium">{formatNumber(rowTotal.toFixed(2))}</td>
                <td className="text-right">{formatMoney(amount)}</td>
              </tr>
            )
          })}
        </tbody>
        <tfoot>
          <tr className="font-semibold bg-slate-50">
            <td className="py-2 px-3 sticky left-0 z-10 bg-slate-50">Total</td>
            {cols.map((c) => (
              <td key={c.key} className="text-right px-3">{formatNumber(columnTotals[c.key].toFixed(2))}</td>
            ))}
            <td className="text-right px-3">{formatNumber(grandTotal.toFixed(2))}</td>
            <td className="text-right px-3">{formatMoney(grandAmount)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}
