import { useEffect, useState, type FormEvent } from 'react'
import api from '../api/client'
import type { Employee, LeaveRequest, Paginated, SalaryPayment, Warehouse } from '../types'
import { formatMoney } from '../utils/format'

type Tab = 'employees' | 'salary' | 'leave'

export default function HRPage() {
  const [tab, setTab] = useState<Tab>('employees')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Human Resource</h1>
        <p className="text-sm text-slate-500">Employees, salary payouts and leave management.</p>
      </div>

      <div className="flex gap-2 no-print">
        {(['employees', 'salary', 'leave'] as Tab[]).map((t) => (
          <button key={t} className={tab === t ? 'btn-primary' : 'btn-secondary'} onClick={() => setTab(t)}>
            {t === 'employees' ? 'Employees' : t === 'salary' ? 'Salary Payments' : 'Leave Requests'}
          </button>
        ))}
      </div>

      {tab === 'employees' && <EmployeesTab />}
      {tab === 'salary' && <SalaryTab />}
      {tab === 'leave' && <LeaveTab />}
    </div>
  )
}

// -- Employees ---------------------------------------------------------------

function EmployeesTab() {
  const [employees, setEmployees] = useState<Employee[]>([])
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ employee_number: '', full_name: '', cnic: '', address: '', role: '', warehouse: '', monthly_salary: '', commission_rate: '' })
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)

  function load() {
    api.get<Paginated<Employee> | Employee[]>('employees/', { params: { page_size: 200 } })
      .then((res) => setEmployees(Array.isArray(res.data) ? res.data : res.data.results))
  }

  useEffect(() => {
    load()
    api.get<Paginated<Warehouse> | Warehouse[]>('warehouses/', { params: { page_size: 100 } })
      .then((res) => setWarehouses(Array.isArray(res.data) ? res.data : res.data.results))
  }, [])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      await api.post('employees/', {
        ...form,
        warehouse: form.warehouse ? Number(form.warehouse) : null,
        monthly_salary: form.monthly_salary || '0',
        commission_rate: form.commission_rate || '0',
      })
      setShowForm(false)
      setForm({ employee_number: '', full_name: '', cnic: '', address: '', role: '', warehouse: '', monthly_salary: '', commission_rate: '' })
      load()
    } catch (err: any) {
      setError(err?.response?.data ? JSON.stringify(err.response.data) : 'Could not create employee.')
    }
  }

  async function terminate(emp: Employee) {
    if (!confirm(`Terminate ${emp.full_name}?`)) return
    setBusyId(emp.id)
    try {
      await api.post(`employees/${emp.id}/terminate/`)
      load()
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-end no-print">
        <button className="btn-primary" onClick={() => setShowForm((s) => !s)}>{showForm ? 'Cancel' : '+ New Employee'}</button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="card p-4 space-y-3 no-print">
          <div className="grid grid-cols-3 gap-3">
            <input className="input" placeholder="Employee number" value={form.employee_number} onChange={(e) => setForm({ ...form, employee_number: e.target.value })} required />
            <input className="input" placeholder="Full name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
            <input className="input" placeholder="CNIC" value={form.cnic} onChange={(e) => setForm({ ...form, cnic: e.target.value })} required />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <input className="input" placeholder="Role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} required />
            <select className="input" value={form.warehouse} onChange={(e) => setForm({ ...form, warehouse: e.target.value })}>
              <option value="">Warehouse...</option>
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
            <input className="input" placeholder="Address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <input className="input" type="number" step="0.01" placeholder="Monthly salary" value={form.monthly_salary} onChange={(e) => setForm({ ...form, monthly_salary: e.target.value })} />
            <input className="input" type="number" step="0.01" placeholder="Commission rate" value={form.commission_rate} onChange={(e) => setForm({ ...form, commission_rate: e.target.value })} />
          </div>
          <button type="submit" className="btn-primary">Save Employee</button>
          {error && <div className="text-sm text-red-600">{error}</div>}
        </form>
      )}

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr><th>Emp #</th><th>Name</th><th>Role</th><th>Warehouse</th><th className="text-right">Salary</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {employees.map((emp) => (
              <tr key={emp.id}>
                <td className="font-mono text-xs">{emp.employee_number}</td>
                <td>{emp.full_name}</td>
                <td>{emp.role}</td>
                <td>{emp.warehouse_name || '—'}</td>
                <td className="text-right">Rs {formatMoney(emp.monthly_salary)}</td>
                <td><span className={`badge ${emp.status === 'ACTIVE' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>{emp.status}</span></td>
                <td className="text-right">
                  {emp.status === 'ACTIVE' && (
                    <button className="btn-secondary no-print" disabled={busyId === emp.id} onClick={() => terminate(emp)}>Terminate</button>
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

// -- Salary payments -----------------------------------------------------------

function SalaryTab() {
  const [payments, setPayments] = useState<SalaryPayment[]>([])
  const [employees, setEmployees] = useState<Employee[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ employee: '', year: String(new Date().getFullYear()), month: String(new Date().getMonth() + 1), salary_paid: '', commission_amount: '' })
  const [error, setError] = useState('')

  function load() {
    api.get<Paginated<SalaryPayment> | SalaryPayment[]>('salary-payments/', { params: { page_size: 200 } })
      .then((res) => setPayments(Array.isArray(res.data) ? res.data : res.data.results))
  }

  useEffect(() => {
    load()
    api.get<Paginated<Employee> | Employee[]>('employees/', { params: { page_size: 200, status: 'ACTIVE' } })
      .then((res) => setEmployees(Array.isArray(res.data) ? res.data : res.data.results))
  }, [])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      await api.post('salary-payments/', {
        employee: Number(form.employee), year: Number(form.year), month: Number(form.month),
        salary_paid: form.salary_paid, commission_amount: form.commission_amount || '0',
      })
      setShowForm(false)
      setForm({ ...form, salary_paid: '', commission_amount: '' })
      load()
    } catch (err: any) {
      setError(err?.response?.data ? JSON.stringify(err.response.data) : 'Could not record salary payment.')
    }
  }

  const totalThisPage = payments.reduce((sum, p) => sum + Number(p.total_paid), 0)

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center no-print">
        <button className="btn-secondary" onClick={() => window.print()}>Print payouts</button>
        <button className="btn-primary" onClick={() => setShowForm((s) => !s)}>{showForm ? 'Cancel' : '+ Record Payment'}</button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="card p-4 space-y-3 no-print">
          <div className="grid grid-cols-4 gap-3">
            <select className="input" value={form.employee} onChange={(e) => setForm({ ...form, employee: e.target.value })} required>
              <option value="">Employee...</option>
              {employees.map((emp) => <option key={emp.id} value={emp.id}>{emp.employee_number} - {emp.full_name}</option>)}
            </select>
            <input className="input" type="number" placeholder="Year" value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} required />
            <input className="input" type="number" min="1" max="12" placeholder="Month" value={form.month} onChange={(e) => setForm({ ...form, month: e.target.value })} required />
            <input className="input" type="number" step="0.01" placeholder="Salary paid" value={form.salary_paid} onChange={(e) => setForm({ ...form, salary_paid: e.target.value })} required />
          </div>
          <input className="input max-w-xs" type="number" step="0.01" placeholder="Commission amount" value={form.commission_amount} onChange={(e) => setForm({ ...form, commission_amount: e.target.value })} />
          <button type="submit" className="btn-primary">Save Payment</button>
          {error && <div className="text-sm text-red-600">{error}</div>}
        </form>
      )}

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr><th>Emp #</th><th>Name</th><th>Month/Year</th><th className="text-right">Salary</th><th className="text-right">Commission</th><th className="text-right">Total</th></tr>
          </thead>
          <tbody>
            {payments.length === 0 ? (
              <tr><td colSpan={6} className="text-center text-slate-400 py-6">No salary payments recorded yet.</td></tr>
            ) : payments.map((p) => (
              <tr key={p.id}>
                <td className="font-mono text-xs">{p.employee_number}</td>
                <td>{p.employee_name}</td>
                <td>{p.month}/{p.year}</td>
                <td className="text-right">Rs {formatMoney(p.salary_paid)}</td>
                <td className="text-right">Rs {formatMoney(p.commission_amount)}</td>
                <td className="text-right font-medium">Rs {formatMoney(p.total_paid)}</td>
              </tr>
            ))}
            {payments.length > 0 && (
              <tr className="font-semibold"><td colSpan={5}>Total (this page)</td><td className="text-right">Rs {formatMoney(totalThisPage)}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// -- Leave requests -----------------------------------------------------------

function LeaveTab() {
  const [leaves, setLeaves] = useState<LeaveRequest[]>([])
  const [busyId, setBusyId] = useState<number | null>(null)

  function load() {
    api.get<Paginated<LeaveRequest> | LeaveRequest[]>('leave-requests/', { params: { page_size: 200 } })
      .then((res) => setLeaves(Array.isArray(res.data) ? res.data : res.data.results))
  }

  useEffect(load, [])

  async function decide(leave: LeaveRequest, approve: boolean) {
    setBusyId(leave.id)
    try {
      await api.post(`leave-requests/${leave.id}/${approve ? 'approve' : 'reject'}/`)
      load()
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="card overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr><th>Employee</th><th>Type</th><th>Dates</th><th className="text-right">Days</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          {leaves.length === 0 ? (
            <tr><td colSpan={6} className="text-center text-slate-400 py-6">No leave requests yet.</td></tr>
          ) : leaves.map((l) => (
            <tr key={l.id}>
              <td>{l.employee_name}</td>
              <td>{l.leave_type}</td>
              <td>{l.start_date} &rarr; {l.end_date}</td>
              <td className="text-right">{l.days}</td>
              <td>
                <span className={`badge ${l.status === 'APPROVED' ? 'bg-emerald-100 text-emerald-700' : l.status === 'REJECTED' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>{l.status}</span>
              </td>
              <td className="text-right space-x-2 no-print">
                {l.status === 'PENDING' && (
                  <>
                    <button className="btn-secondary" disabled={busyId === l.id} onClick={() => decide(l, true)}>Approve</button>
                    <button className="btn-secondary" disabled={busyId === l.id} onClick={() => decide(l, false)}>Reject</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
