import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { Link } from 'react-router-dom'
import api from '../api/client'
import MonthPicker, { monthLabel } from '../components/MonthPicker'
import StatCard from '../components/StatCard'
import type { DashboardData } from '../types'
import { formatM, formatMoney, formatNumber, formatRsShort } from '../utils/format'

const ACTUAL_COLOR = '#1d4ed8'
const COMPANY_COLOR = '#94a3b8'

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [month, setMonth] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    api
      .get<DashboardData>('reports/dashboard/', { params: month ? { month } : {} })
      .then((res) => {
        setData(res.data)
        setMonth(res.data.month)
      })
      .catch(() => setError('Could not load dashboard data.'))
      .finally(() => setLoading(false))
  }, [month])

  if (loading && !data) return <div className="text-slate-500">Loading dashboard...</div>
  if (error) return <div className="text-red-600">{error}</div>
  if (!data) return null

  const daily = data.daily.map((row) => ({
    day: row.day.slice(8),
    Actual: row.actual_value,
    'Company (BIZOM)': row.company_value,
  }))
  const brands = data.brands.map((row) => ({
    brand: row.brand,
    Actual: Math.round(row.actual_m),
    'Company (BIZOM)': Math.round(row.company_m),
  }))
  const s = data.settlements
  const gapPct = data.company_sales_value ? (data.gap_value / data.company_sales_value) * 100 : 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Owner Dashboard &mdash; {monthLabel(data.month)}</h1>
          <p className="text-sm text-slate-500">
            Actual sales (what DRs physically sold) beside the company version in BIZOM. Loaded from your
            September BIZOM export and daily actual-sale sheet.
          </p>
        </div>
        {data.months.length > 0 && <MonthPicker months={data.months} value={data.month} onChange={setMonth} />}
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Actual sales" value={formatRsShort(data.actual_sales_value)} hint={formatM(data.actual_sales_m)} />
        <StatCard label="Company sales (BIZOM)" value={formatRsShort(data.company_sales_value)} hint={formatM(data.company_sales_m)} />
        <StatCard
          label="Madam gap (BIZOM − actual)"
          value={formatRsShort(data.gap_value)}
          hint={`${formatM(data.gap_m)} · ${gapPct.toFixed(1)}% of BIZOM`}
          tone="warning"
        />
        <StatCard
          label="Net profit (actual book)"
          value={formatRsShort(data.net_profit)}
          hint={`Gross margin ${data.gross_margin_pct}% · gross ${formatRsShort(data.gross_profit)}`}
          tone="good"
        />
        <StatCard label="Stock on hand (all godowns)" value={formatRsShort(data.stock_value)} hint="At PTC invoice rate" />
        <StatCard
          label="Held in adjusted godown"
          value={formatRsShort(data.adjusted_stock_value)}
          hint="Madam Banam stock, kept apart"
          tone="warning"
        />
        <StatCard
          label="DR collections"
          value={formatRsShort((s.cash ?? 0) + (s.bank ?? 0))}
          hint={`Cash ${formatRsShort(s.cash)} · Bank ${formatRsShort(s.bank)}`}
          tone="good"
        />
        <StatCard
          label="Low stock alerts"
          value={formatNumber(data.low_stock_alerts)}
          tone={data.low_stock_alerts > 0 ? 'warning' : 'good'}
          hint="Below 3 days of actual sales"
        />
      </div>

      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-medium text-slate-600">Daily sales value: actual vs company</div>
          <Link to="/company-vs-actual" className="text-sm text-brand-600 hover:underline no-print">Full comparison &rarr;</Link>
        </div>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={daily}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="day" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} width={80} tickFormatter={(v) => formatRsShort(v).replace('Rs ', '')} />
            <Tooltip formatter={(v: number) => `Rs ${formatMoney(v)}`} labelFormatter={(d) => `Day ${d}`} />
            <Legend />
            <Line type="monotone" dataKey="Company (BIZOM)" stroke={COMPANY_COLOR} strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="Actual" stroke={ACTUAL_COLOR} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card p-4 lg:col-span-2">
          <div className="text-sm font-medium text-slate-600 mb-3">Volume by brand (M): actual vs company</div>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={brands} layout="vertical" margin={{ left: 40 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v) => formatNumber(v)} />
              <YAxis type="category" dataKey="brand" tick={{ fontSize: 11 }} width={130} />
              <Tooltip formatter={(v: number) => formatM(v)} />
              <Legend />
              <Bar dataKey="Company (BIZOM)" fill={COMPANY_COLOR} radius={[0, 3, 3, 0]} />
              <Bar dataKey="Actual" fill={ACTUAL_COLOR} radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="space-y-4">
          <div className="card p-4">
            <div className="text-sm font-medium text-slate-600 mb-2">DR settlements this month</div>
            <dl className="text-sm space-y-1.5">
              <Row label="Slips settled" value={formatNumber(s.count)} />
              <Row label="Cash received" value={`Rs ${formatMoney(s.cash)}`} />
              <Row label="Bank transfers" value={`Rs ${formatMoney(s.bank)}`} />
              <Row label="Market credit" value={`Rs ${formatMoney(s.market_credit)}`} />
              <Row label="FBR" value={`Rs ${formatMoney(s.fbr)}`} />
              <Row label="Madam Banam" value={`Rs ${formatMoney(s.banam)}`} />
              <Row label="Madam Wasooli" value={`Rs ${formatMoney(s.wasooli)}`} />
              <Row label="DR shortages" value={`Rs ${formatMoney(s.short)}`} warn />
            </dl>
            <Link to="/settlements" className="mt-3 inline-block text-sm text-brand-600 hover:underline no-print">Open cash settlements &rarr;</Link>
          </div>
          <div className="card p-4">
            <div className="text-sm font-medium text-slate-600 mb-2">Stock by godown</div>
            <dl className="text-sm space-y-1.5">
              {data.stock_by_warehouse.map((w) => (
                <Row key={w.code} label={w.warehouse} value={`${formatM(w.m)} · ${formatRsShort(w.value)}`} />
              ))}
            </dl>
          </div>
        </div>
      </div>
    </div>
  )
}

function Row({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className={`font-medium text-right ${warn ? 'text-amber-600' : ''}`}>{value}</dd>
    </div>
  )
}
