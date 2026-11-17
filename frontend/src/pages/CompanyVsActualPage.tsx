import { useEffect, useState } from 'react'
import api from '../api/client'
import MonthPicker, { monthLabel } from '../components/MonthPicker'
import type { ComparisonRow } from '../types'
import { formatM, formatMoney } from '../utils/format'

type Group = 'dr' | 'brand' | 'sku' | 'day' | 'madam'

const TABS: { key: Group; label: string }[] = [
  { key: 'dr', label: 'By DR' },
  { key: 'brand', label: 'By brand' },
  { key: 'sku', label: 'By SKU' },
  { key: 'day', label: 'By day' },
  { key: 'madam', label: 'Madam register' },
]

interface ComparisonResponse {
  month: string
  months: string[]
  rows: ComparisonRow[]
  totals: Record<string, number>
}

interface MadamDay {
  date: string
  banam_fmc: number
  banam_nc: number
  wasooli: number
  total_sale: number
  net: number
  running: number
}

interface MadamResponse {
  month: string
  months: string[]
  days: MadamDay[]
  adjusted_stock: { sku_name: string; brand: string; m: number; value: number }[]
}

export default function CompanyVsActualPage() {
  const [group, setGroup] = useState<Group>('dr')
  const [month, setMonth] = useState('')
  const [months, setMonths] = useState<string[]>([])
  const [data, setData] = useState<ComparisonResponse | null>(null)
  const [madam, setMadam] = useState<MadamResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const params = month ? { month } : {}
    const request = group === 'madam'
      ? api.get<MadamResponse>('reports/madam-register/', { params }).then((res) => {
          setMadam(res.data)
          return res.data
        })
      : api.get<ComparisonResponse>('reports/company-vs-actual/', { params: { ...params, group } }).then((res) => {
          setData(res.data)
          return res.data
        })
    request
      .then((res) => {
        setMonths(res.months)
        setMonth(res.month)
      })
      .finally(() => setLoading(false))
  }, [group, month])

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Company vs Actual{month && ` — ${monthLabel(month)}`}</h1>
          <p className="text-sm text-slate-500 max-w-3xl">
            Company = BIZOM invoices. Actual = your daily actual-sale sheet. A positive gap is stock invoiced in
            BIZOM but not physically sold (Madam Banam); a negative gap is stock sold without a BIZOM invoice
            (Madam Wasooli).
          </p>
        </div>
        <div className="flex gap-2 no-print">
          {months.length > 0 && <MonthPicker months={months} value={month} onChange={setMonth} />}
          <button className="btn-secondary" onClick={() => window.print()}>Print</button>
        </div>
      </div>

      <div className="flex gap-1 border-b border-slate-200 no-print">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setGroup(tab.key)}
            className={`px-4 py-2 text-sm -mb-px border-b-2 ${
              group === tab.key ? 'border-brand-500 text-brand-600 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading && <div className="text-slate-500 text-sm">Loading...</div>}
      {!loading && group !== 'madam' && data && <ComparisonTable data={data} group={group} />}
      {!loading && group === 'madam' && madam && <MadamRegister data={madam} />}
    </div>
  )
}

function gapClass(value: number) {
  if (value > 0.5) return 'text-amber-700'
  if (value < -0.5) return 'text-emerald-700'
  return 'text-slate-500'
}

function ComparisonTable({ data, group }: { data: ComparisonResponse; group: Group }) {
  const t = data.totals
  const heading = { dr: 'DR', brand: 'Brand', sku: 'SKU', day: 'Date', madam: '' }[group]
  const anyAssumed = data.rows.some((r) => r.assumed)
  return (
    <div className="card overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr>
            <th>{heading}</th>
            <th className="text-right">Company M</th>
            <th className="text-right">Actual M</th>
            <th className="text-right">Gap M</th>
            <th className="text-right">Company Rs</th>
            <th className="text-right">Actual Rs</th>
            <th className="text-right">Gap Rs</th>
            <th className="text-right">Gap %</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.key}>
              <td>
                {group === 'dr' ? (
                  <>
                    <div className="font-medium">{r.label}</div>
                    <div className="text-xs text-slate-400">{r.key}{r.assumed && ' · not on actual sheet'}</div>
                  </>
                ) : r.label}
              </td>
              <td className="text-right">{formatM(r.company_m)}</td>
              <td className="text-right">{formatM(r.actual_m)}</td>
              <td className={`text-right font-medium ${gapClass(r.gap_m)}`}>{formatM(r.gap_m)}</td>
              <td className="text-right">{formatMoney(r.company_value)}</td>
              <td className="text-right">{formatMoney(r.actual_value)}</td>
              <td className={`text-right font-medium ${gapClass(r.gap_value)}`}>{formatMoney(r.gap_value)}</td>
              <td className={`text-right ${gapClass(r.gap_value)}`}>{r.gap_pct == null ? '—' : `${r.gap_pct}%`}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="font-semibold bg-slate-50">
            <td className="py-2 px-3">Total</td>
            <td className="text-right px-3">{formatM(t.company_m)}</td>
            <td className="text-right px-3">{formatM(t.actual_m)}</td>
            <td className={`text-right px-3 ${gapClass(t.gap_m)}`}>{formatM(t.gap_m)}</td>
            <td className="text-right px-3">{formatMoney(t.company_value)}</td>
            <td className="text-right px-3">{formatMoney(t.actual_value)}</td>
            <td className={`text-right px-3 ${gapClass(t.gap_value)}`}>{formatMoney(t.gap_value)}</td>
            <td className="text-right px-3">
              {t.company_value ? `${((t.gap_value / t.company_value) * 100).toFixed(1)}%` : '—'}
            </td>
          </tr>
        </tfoot>
      </table>
      {anyAssumed && (
        <p className="text-xs text-slate-500 px-3 py-2">
          &ldquo;Not on actual sheet&rdquo;: shop sale and SS/RTF routes have BIZOM sales but no row on the actual-sale
          sheet, so their BIZOM volume is taken as actual until we get their real figures.
        </p>
      )}
    </div>
  )
}

function MadamRegister({ data }: { data: MadamResponse }) {
  const total = data.days.reduce(
    (acc, d) => ({ fmc: acc.fmc + d.banam_fmc, nc: acc.nc + d.banam_nc, w: acc.w + d.wasooli }),
    { fmc: 0, nc: 0, w: 0 },
  )
  const heldValue = data.adjusted_stock.reduce((sum, r) => sum + r.value, 0)
  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <div className="card overflow-x-auto xl:col-span-2">
        <div className="px-4 pt-4 text-sm font-medium text-slate-600">Daily adjustments from DR settlements</div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Date</th>
              <th className="text-right">BIZOM sale</th>
              <th className="text-right">Banam FMC</th>
              <th className="text-right">Banam NC</th>
              <th className="text-right">Wasooli</th>
              <th className="text-right">Net</th>
              <th className="text-right">Running balance</th>
            </tr>
          </thead>
          <tbody>
            {data.days.map((d) => (
              <tr key={d.date}>
                <td>{d.date}</td>
                <td className="text-right">{formatMoney(d.total_sale)}</td>
                <td className="text-right">{formatMoney(d.banam_fmc)}</td>
                <td className="text-right">{formatMoney(d.banam_nc)}</td>
                <td className="text-right text-emerald-700">{formatMoney(d.wasooli)}</td>
                <td className={`text-right ${gapClass(d.net)}`}>{formatMoney(d.net)}</td>
                <td className="text-right font-medium">{formatMoney(d.running)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="font-semibold bg-slate-50">
              <td className="py-2 px-3">Total</td>
              <td />
              <td className="text-right px-3">{formatMoney(total.fmc)}</td>
              <td className="text-right px-3">{formatMoney(total.nc)}</td>
              <td className="text-right px-3">{formatMoney(total.w)}</td>
              <td className="text-right px-3">{formatMoney(total.fmc + total.nc - total.w)}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
      <div className="card overflow-x-auto">
        <div className="px-4 pt-4 text-sm font-medium text-slate-600">Stock held in the adjusted godown</div>
        <div className="px-4 text-xs text-slate-400">Valued at PTC invoice rate: Rs {formatMoney(heldValue)}</div>
        <table className="data-table">
          <thead>
            <tr><th>SKU</th><th className="text-right">M</th><th className="text-right">Rs</th></tr>
          </thead>
          <tbody>
            {data.adjusted_stock.map((r) => (
              <tr key={r.sku_name}>
                <td>{r.sku_name}</td>
                <td className="text-right">{formatM(r.m)}</td>
                <td className="text-right">{formatMoney(r.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
