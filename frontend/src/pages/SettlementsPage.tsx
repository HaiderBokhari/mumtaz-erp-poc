import { useEffect, useMemo, useState, type FormEvent } from 'react'
import api from '../api/client'
import type { DRSettlement, Paginated, PayoutRow, Warehouse } from '../types'
import { formatMoney } from '../utils/format'

const DENOMINATIONS = [5000, 1000, 500, 100, 50, 20, 10] as const
type NoteKey = `notes_${(typeof DENOMINATIONS)[number]}`

const EMPTY_FORM = {
  dr: '', date: '', total_sale: '', fbr: '', scattered_wholesale: '0',
  madam_banam_fmc: '0', madam_banam_nc: '0', madam_wasooli: '0',
  notes_5000: '0', notes_1000: '0', notes_500: '0', notes_100: '0', notes_50: '0', notes_20: '0', notes_10: '0',
  bank_transfer_1: '0', bank_transfer_2: '0', bank_transfer_3: '0', expense: '0', market_credit: '0', remarks: '',
}

const n = (v: string | number | undefined) => Number(v || 0)

function differenceTone(diff: number) {
  if (Math.abs(diff) < 1) return 'text-emerald-700'
  return diff > 0 ? 'text-red-600' : 'text-amber-700'
}

export default function SettlementsPage() {
  const [date, setDate] = useState('')
  const [rows, setRows] = useState<DRSettlement[]>([])
  const [selected, setSelected] = useState<DRSettlement | null>(null)
  const [drs, setDrs] = useState<PayoutRow[]>([])
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Open on the latest day that has slips.
    api.get<Paginated<DRSettlement>>('dr-settlements/', { params: { ordering: '-date', page_size: 1 } })
      .then((res) => setDate(res.data.results[0]?.date ?? new Date().toISOString().slice(0, 10)))
    api.get<{ rows: PayoutRow[] }>('reports/dr-payout/').then((res) => setDrs(res.data.rows))
    api.get<Paginated<Warehouse> | Warehouse[]>('warehouses/')
      .then((res) => setWarehouses(Array.isArray(res.data) ? res.data : res.data.results))
  }, [])

  function load() {
    if (!date) return
    setLoading(true)
    api.get<Paginated<DRSettlement>>('dr-settlements/', { params: { date, page_size: 100 } })
      .then((res) => {
        const sorted = [...res.data.results].sort((a, b) => a.dr_code.localeCompare(b.dr_code))
        setRows(sorted)
        setSelected((current) => sorted.find((r) => r.id === current?.id) ?? null)
      })
      .finally(() => setLoading(false))
  }

  useEffect(load, [date])

  const totals = useMemo(() => rows.reduce((acc, r) => ({
    sale: acc.sale + n(r.total_sale), banam: acc.banam + n(r.total_banam), wasooli: acc.wasooli + n(r.madam_wasooli),
    cash: acc.cash + n(r.total_cash), bank: acc.bank + n(r.total_bank), credit: acc.credit + n(r.market_credit),
    diff: acc.diff + n(r.difference),
  }), { sale: 0, banam: 0, wasooli: 0, cash: 0, bank: 0, credit: 0, diff: 0 }), [rows])

  // Live slip arithmetic for the entry form, same rule as the server.
  const formCash = DENOMINATIONS.reduce((sum, d) => sum + d * n(form[`notes_${d}` as NoteKey]), 0)
  const formTotal = formCash + n(form.bank_transfer_1) + n(form.bank_transfer_2) + n(form.bank_transfer_3)
    + n(form.expense) + n(form.market_credit) + n(form.madam_banam_fmc) + n(form.madam_banam_nc) + n(form.fbr)
  const formDiff = n(form.total_sale) + n(form.madam_wasooli) - formTotal

  async function handleSave(e: FormEvent) {
    e.preventDefault()
    setError('')
    const hq = warehouses.find((w) => w.is_head_office) ?? warehouses[0]
    try {
      const res = await api.post<DRSettlement>('dr-settlements/', {
        ...form, dr: Number(form.dr), date: form.date || date, warehouse: hq?.id,
      })
      setShowForm(false)
      setForm(EMPTY_FORM)
      setDate(res.data.date)
      load()
      setSelected(res.data)
    } catch (err: any) {
      setError(err?.response?.data ? JSON.stringify(err.response.data) : 'Could not save the slip.')
    }
  }

  function field(key: keyof typeof EMPTY_FORM, label: string, props: Record<string, unknown> = {}) {
    return (
      <label className="block">
        <span className="text-xs text-slate-500">{label}</span>
        <input
          className="input" value={form[key]} type="number" step="0.01"
          onChange={(e) => setForm({ ...form, [key]: e.target.value })} {...props}
        />
      </label>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">DR Cash Settlement</h1>
          <p className="text-sm text-slate-500 max-w-3xl">
            The end-of-day slip, as on paper: the KPO enters the sale, FBR and Madam adjustments; the DR&rsquo;s
            cash, transfers, expense and market credit are counted against it. Difference = short (red) or
            excess (amber).
          </p>
        </div>
        <div className="flex gap-2 no-print">
          <input type="date" className="input w-auto" value={date} onChange={(e) => setDate(e.target.value)} />
          <button className="btn-secondary" onClick={() => window.print()}>Print</button>
          <button className="btn-primary" onClick={() => { setShowForm((s) => !s); setForm({ ...EMPTY_FORM, date }) }}>
            {showForm ? 'Cancel' : 'New slip'}
          </button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={handleSave} className="card p-4 space-y-4 no-print">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-3">
              <div className="text-sm font-semibold text-slate-700">Portion filled by KPO</div>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-xs text-slate-500">DR</span>
                  <select className="input" required value={form.dr} onChange={(e) => setForm({ ...form, dr: e.target.value })}>
                    <option value="">Select DR</option>
                    {drs.map((d) => <option key={d.dr_id} value={d.dr_id}>{d.name} ({d.dr_code.replace('SGD_SGD_', '')})</option>)}
                  </select>
                </label>
                <label className="block">
                  <span className="text-xs text-slate-500">Date</span>
                  <input className="input" type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
                </label>
                {field('total_sale', 'Total sale (BIZOM)', { required: true })}
                {field('fbr', 'FBR')}
                {field('scattered_wholesale', 'Scattered wholesale')}
                {field('madam_banam_fmc', 'Adjustment FMC (Madam Banam)')}
                {field('madam_banam_nc', 'Adjustment NC (Madam Banam)')}
                {field('madam_wasooli', 'Madam Wasooli')}
              </div>
            </div>
            <div className="space-y-3">
              <div className="text-sm font-semibold text-slate-700">Portion filled by DR</div>
              <div className="grid grid-cols-4 gap-2">
                {DENOMINATIONS.map((d) => (
                  <label key={d} className="block">
                    <span className="text-xs text-slate-500">Rs {d} &times;</span>
                    <input
                      className="input" type="number" min="0" value={form[`notes_${d}` as NoteKey]}
                      onChange={(e) => setForm({ ...form, [`notes_${d}`]: e.target.value })}
                    />
                  </label>
                ))}
                <div className="flex flex-col justify-end text-sm">
                  <span className="text-xs text-slate-500">Total cash</span>
                  <span className="font-semibold py-2">Rs {formatMoney(formCash)}</span>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                {field('bank_transfer_1', 'Bank transfer')}
                {field('bank_transfer_2', 'Bank transfer')}
                {field('bank_transfer_3', 'Bank transfer')}
                {field('expense', 'Expense if any')}
                {field('market_credit', 'Market credit')}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
            <div className="text-sm">
              Total <span className="font-semibold">Rs {formatMoney(formTotal)}</span>
              <span className="mx-3 text-slate-300">|</span>
              Difference <span className={`font-semibold ${differenceTone(formDiff)}`}>Rs {formatMoney(formDiff)}</span>
            </div>
            <div className="flex gap-2">
              <input className="input w-72" placeholder="Remarks" value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} />
              <button className="btn-primary" type="submit">Save slip</button>
            </div>
          </div>
          {error && <div className="text-sm text-red-600">{error}</div>}
        </form>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        <div className="card overflow-x-auto xl:col-span-3">
          <table className="data-table">
            <thead>
              <tr>
                <th>DR</th>
                <th className="text-right">Sale</th>
                <th className="text-right">Banam</th>
                <th className="text-right">Cash</th>
                <th className="text-right">Bank</th>
                <th className="text-right">Credit</th>
                <th className="text-right">Diff</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={7} className="text-slate-400">Loading...</td></tr>}
              {!loading && rows.length === 0 && <tr><td colSpan={7} className="text-slate-400">No slips for this date.</td></tr>}
              {rows.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setSelected(r)}
                  className={`cursor-pointer hover:bg-slate-50 ${selected?.id === r.id ? 'bg-brand-50' : ''}`}
                >
                  <td>
                    <div className="font-medium">{r.dr_name}</div>
                    <div className="text-xs text-slate-400">{r.dr_code.replace('SGD_SGD_', '')}</div>
                  </td>
                  <td className="text-right">{formatMoney(r.total_sale)}</td>
                  <td className="text-right">{formatMoney(r.total_banam)}</td>
                  <td className="text-right">{formatMoney(r.total_cash)}</td>
                  <td className="text-right">{formatMoney(r.total_bank)}</td>
                  <td className="text-right">{formatMoney(r.market_credit)}</td>
                  <td className={`text-right font-medium ${differenceTone(n(r.difference))}`}>{formatMoney(r.difference)}</td>
                </tr>
              ))}
            </tbody>
            {rows.length > 0 && (
              <tfoot>
                <tr className="font-semibold bg-slate-50">
                  <td className="py-2 px-3">Total ({rows.length})</td>
                  <td className="text-right px-3">{formatMoney(totals.sale)}</td>
                  <td className="text-right px-3">{formatMoney(totals.banam)}</td>
                  <td className="text-right px-3">{formatMoney(totals.cash)}</td>
                  <td className="text-right px-3">{formatMoney(totals.bank)}</td>
                  <td className="text-right px-3">{formatMoney(totals.credit)}</td>
                  <td className={`text-right px-3 ${differenceTone(totals.diff)}`}>{formatMoney(totals.diff)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>

        <div className="xl:col-span-2">
          {selected ? <Slip s={selected} onPosted={load} /> : (
            <div className="card p-6 text-sm text-slate-400">Select a DR to see the slip.</div>
          )}
        </div>
      </div>
    </div>
  )
}

function Slip({ s, onPosted }: { s: DRSettlement; onPosted: () => void }) {
  const [posting, setPosting] = useState(false)
  const diff = n(s.difference)
  const line = (label: string, value: string | number, strong = false) => (
    <tr className={strong ? 'font-semibold' : ''}>
      <td className="border border-slate-300 px-3 py-1">{label}</td>
      <td className="border border-slate-300 px-3 py-1 text-right">{formatMoney(value)}</td>
    </tr>
  )
  async function post() {
    setPosting(true)
    try {
      await api.post(`dr-settlements/${s.id}/post_to_ledger/`)
      onPosted()
    } finally {
      setPosting(false)
    }
  }
  return (
    <div className="card p-4 space-y-4">
      <table className="w-full text-sm border-collapse">
        <tbody>
          <tr><td className="border border-slate-300 px-3 py-1">Date</td><td className="border border-slate-300 px-3 py-1 text-right">{s.date}</td></tr>
          <tr><td className="border border-slate-300 px-3 py-1">DR name</td><td className="border border-slate-300 px-3 py-1 text-right font-medium">{s.dr_name}</td></tr>
          {line('Total sale', s.total_sale)}
          {line('FBR', s.fbr)}
          {line('Scattered whole sale', s.scattered_wholesale)}
          {line('Adjustment FMC banam madam', s.madam_banam_fmc)}
          {line('Adjustment NC banam madam', s.madam_banam_nc)}
          {n(s.madam_wasooli) > 0 && line('Madam wasooli', s.madam_wasooli)}
        </tbody>
      </table>
      <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Portion filled by DR</div>
      <table className="w-full text-sm border-collapse">
        <tbody>
          {DENOMINATIONS.map((d) => {
            const count = s[`notes_${d}` as NoteKey]
            return (
              <tr key={d}>
                <td className="border border-slate-300 px-3 py-1">{d} &times; {count}</td>
                <td className="border border-slate-300 px-3 py-1 text-right">{formatMoney(d * count)}</td>
              </tr>
            )
          })}
          {line('Total cash', s.total_cash, true)}
          {line('Bank transfer', s.bank_transfer_1)}
          {n(s.bank_transfer_2) > 0 && line('Bank transfer', s.bank_transfer_2)}
          {n(s.bank_transfer_3) > 0 && line('Bank transfer', s.bank_transfer_3)}
          {line('Expense if any', s.expense)}
          {line('Market credit', s.market_credit)}
          {line('Total', s.total_accounted, true)}
          <tr className="font-semibold">
            <td className="border border-slate-300 px-3 py-1">Difference</td>
            <td className={`border border-slate-300 px-3 py-1 text-right ${differenceTone(diff)}`}>{formatMoney(diff)}</td>
          </tr>
        </tbody>
      </table>
      {s.remarks && <p className="text-xs text-slate-500">{s.remarks}</p>}
      <div className="flex items-center justify-between no-print">
        <span className={`badge ${s.is_posted ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
          {s.is_posted ? 'Posted to accounts' : 'Not posted'}
        </span>
        {!s.is_posted && (
          <button className="btn-secondary" disabled={posting} onClick={post}>Post to accounts</button>
        )}
      </div>
    </div>
  )
}
