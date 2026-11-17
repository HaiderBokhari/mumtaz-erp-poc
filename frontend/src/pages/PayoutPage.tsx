import { useEffect, useState } from 'react'
import api from '../api/client'
import MonthPicker, { monthLabel } from '../components/MonthPicker'
import type { PayoutRow } from '../types'
import { formatM, formatMoney } from '../utils/format'

interface PayoutResponse {
  month: string
  months: string[]
  rows: PayoutRow[]
  totals: Record<string, number>
}

export default function PayoutPage() {
  const [month, setMonth] = useState('')
  const [data, setData] = useState<PayoutResponse | null>(null)

  useEffect(() => {
    api.get<PayoutResponse>('reports/dr-payout/', { params: month ? { month } : {} }).then((res) => {
      setData(res.data)
      setMonth(res.data.month)
    })
  }, [month])

  if (!data) return <div className="text-slate-500">Loading...</div>
  const rows = data.rows.filter((r) => Number(r.actual_m) > 0)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">DR Salary &amp; Commission &mdash; {monthLabel(data.month)}</h1>
          <p className="text-sm text-slate-500 max-w-3xl">
            Your revised salary structure (fixed + attendance + target + VR allowance) plus brand-wise commission
            per M on what each DR actually sold. Target bonus is paid only when actual volume meets the month&rsquo;s
            target. Attendance is assumed full until biometric attendance is connected.
          </p>
        </div>
        <div className="flex gap-2 no-print">
          <MonthPicker months={data.months} value={data.month} onChange={setMonth} />
          <button className="btn-secondary" onClick={() => window.print()}>Print</button>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>DR</th>
              <th>Grade</th>
              <th className="text-right">Actual</th>
              <th className="text-right">Target</th>
              <th className="text-right">Achieved</th>
              <th className="text-right">Fixed</th>
              <th className="text-right">Attendance</th>
              <th className="text-right">Target bonus</th>
              <th className="text-right">VR</th>
              <th className="text-right">Commission</th>
              <th className="text-right">Total payable</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.dr_id}>
                <td>
                  <div className="font-medium">{r.name}</div>
                  <div className="text-xs text-slate-400">{r.dr_code.replace('SGD_SGD_', '')}{r.assumed && ' · BIZOM volume'}</div>
                </td>
                <td>{r.grade}</td>
                <td className="text-right">{formatM(r.actual_m)}</td>
                <td className="text-right">{r.target_m ? formatM(r.target_m) : '—'}</td>
                <td className="text-right">
                  {r.achievement_pct == null ? '—' : (
                    <span className={`badge ${r.target_achieved ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                      {r.achievement_pct}%
                    </span>
                  )}
                </td>
                <td className="text-right">{formatMoney(r.fixed)}</td>
                <td className="text-right">{formatMoney(r.attendance)}</td>
                <td className="text-right">{formatMoney(r.target_bonus)}</td>
                <td className="text-right">{formatMoney(r.vr_allowance)}</td>
                <td className="text-right">{formatMoney(r.commission)}</td>
                <td className="text-right font-semibold">{formatMoney(r.total_payable)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="font-semibold bg-slate-50">
              <td className="py-2 px-3" colSpan={2}>Total ({rows.length} DRs)</td>
              <td className="text-right px-3">{formatM(data.totals.actual_m)}</td>
              <td colSpan={6} />
              <td className="text-right px-3">{formatMoney(data.totals.commission)}</td>
              <td className="text-right px-3">{formatMoney(data.totals.total_payable)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        Targets for September are seeded (about ±10% of actual) until the real monthly targets sheet is shared.
      </p>
    </div>
  )
}
