import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import api from '../api/client'
import StatCard from '../components/StatCard'
import type { DashboardData } from '../types'
import { formatMoney, formatNumber } from '../utils/format'

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .get<DashboardData>('reports/dashboard/')
      .then((res) => setData(res.data))
      .catch(() => setError('Could not load dashboard data.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-slate-500">Loading dashboard...</div>
  if (error) return <div className="text-red-600">{error}</div>
  if (!data) return null

  const trend = data.sales_trend_30d.map((row) => ({
    day: row.day.slice(5),
    value: Number(row.value),
  }))
  const channels = data.channel_breakdown_mtd.map((row) => ({
    channel: row.channel__name,
    value: Number(row.value),
  }))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Owner Dashboard</h1>
        <p className="text-sm text-slate-500">Live snapshot across all branches &mdash; no end-of-day wait required.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Stock on hand (value)" value={`Rs ${formatMoney(data.stock_value)}`} />
        <StatCard label="Today's sales" value={`Rs ${formatMoney(data.todays_sales_value)}`} hint={`${formatNumber(data.todays_sales_quantity)} units`} />
        <StatCard label="Month-to-date sales" value={`Rs ${formatMoney(data.mtd_sales_value)}`} />
        <StatCard label="Collections (MTD)" value={`Rs ${formatMoney(data.collections_mtd)}`} tone="good" />
        <StatCard label="Outstanding receivables" value={`Rs ${formatMoney(data.outstanding_receivables)}`} tone="warning" />
        <StatCard label="Open purchase orders" value={formatNumber(data.open_purchase_orders)} />
        <StatCard
          label="Low stock alerts"
          value={formatNumber(data.low_stock_alerts)}
          tone={data.low_stock_alerts > 0 ? 'warning' : 'good'}
          hint="Below configured safety stock"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card p-4 lg:col-span-2">
          <div className="text-sm font-medium text-slate-600 mb-3">Sales value &mdash; last 30 days</div>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="day" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} width={70} tickFormatter={(v) => formatMoney(v)} />
              <Tooltip formatter={(v: number) => `Rs ${formatMoney(v)}`} />
              <Line type="monotone" dataKey="value" stroke="#1d4ed8" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-4">
          <div className="text-sm font-medium text-slate-600 mb-3">Sales by channel (MTD)</div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={channels} layout="vertical" margin={{ left: 24 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v) => formatMoney(v)} />
              <YAxis type="category" dataKey="channel" tick={{ fontSize: 11 }} width={110} />
              <Tooltip formatter={(v: number) => `Rs ${formatMoney(v)}`} />
              <Bar dataKey="value" fill="#1d4ed8" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
