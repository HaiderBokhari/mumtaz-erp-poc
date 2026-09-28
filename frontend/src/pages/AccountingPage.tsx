import { useEffect, useState, type FormEvent } from 'react'
import api from '../api/client'
import type {
  AgedRow, BalanceSheet, CashflowStatement, ChartOfAccount, IncomeStatement,
  Paginated, Party, PartyLedger, Voucher,
} from '../types'
import { formatMoney } from '../utils/format'

type Tab = 'parties' | 'vouchers' | 'statements'

const VOUCHER_TYPES: Voucher['voucher_type'][] = ['PAYMENT', 'EXPENSE', 'JOURNAL']

export default function AccountingPage() {
  const [tab, setTab] = useState<Tab>('parties')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Accounting</h1>
        <p className="text-sm text-slate-500">Party ledgers, vouchers, and financial statements.</p>
      </div>

      <div className="flex gap-2 no-print">
        {(['parties', 'vouchers', 'statements'] as Tab[]).map((t) => (
          <button
            key={t}
            className={tab === t ? 'btn-primary' : 'btn-secondary'}
            onClick={() => setTab(t)}
          >
            {t === 'parties' ? 'Parties & Ledgers' : t === 'vouchers' ? 'Vouchers' : 'Financial Statements'}
          </button>
        ))}
      </div>

      {tab === 'parties' && <PartiesTab />}
      {tab === 'vouchers' && <VouchersTab />}
      {tab === 'statements' && <StatementsTab />}
    </div>
  )
}

// -- Parties & Ledgers -----------------------------------------------------

function PartiesTab() {
  const [parties, setParties] = useState<Party[]>([])
  const [aged, setAged] = useState<{ receivables: AgedRow[]; payables: AgedRow[] } | null>(null)
  const [selected, setSelected] = useState<Party | null>(null)
  const [ledger, setLedger] = useState<PartyLedger | null>(null)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  useEffect(() => {
    api.get<Paginated<Party> | Party[]>('accounting/parties/', { params: { page_size: 500 } })
      .then((res) => setParties(Array.isArray(res.data) ? res.data : res.data.results))
    Promise.all([
      api.get<AgedRow[]>('accounting/parties/aged_receivables/'),
      api.get<AgedRow[]>('accounting/parties/aged_payables/'),
    ]).then(([r, p]) => setAged({ receivables: r.data, payables: p.data }))
  }, [])

  async function openLedger(party: Party) {
    setSelected(party)
    const res = await api.get<PartyLedger>(`accounting/parties/${party.id}/ledger/`, {
      params: { date_from: dateFrom || undefined, date_to: dateTo || undefined },
    })
    setLedger(res.data)
  }

  useEffect(() => {
    if (selected) openLedger(selected)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFrom, dateTo])

  if (selected && ledger) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between no-print">
          <button className="btn-secondary" onClick={() => { setSelected(null); setLedger(null) }}>&larr; Back to parties</button>
          <button className="btn-secondary" onClick={() => window.print()}>Print</button>
        </div>
        <div className="card p-4">
          <h2 className="font-medium">{ledger.party.name}</h2>
          <p className="text-xs text-slate-500">{ledger.party.party_type} &middot; Balance: Rs {formatMoney(ledger.party.balance)}</p>
        </div>
        <div className="flex gap-3 no-print">
          <input className="input max-w-xs" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          <input className="input max-w-xs" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
        <div className="card overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr><th>Date</th><th>Reference</th><th>Narration</th><th className="text-right">Debit</th><th className="text-right">Credit</th><th className="text-right">Balance</th></tr>
            </thead>
            <tbody>
              <tr><td colSpan={5} className="text-slate-500">Opening balance</td><td className="text-right font-medium">Rs {formatMoney(ledger.opening_balance)}</td></tr>
              {ledger.lines.map((line, i) => (
                <tr key={i}>
                  <td>{line.date}</td>
                  <td className="font-mono text-xs">{line.reference}</td>
                  <td>{line.narration}</td>
                  <td className="text-right">{Number(line.debit) ? `Rs ${formatMoney(line.debit)}` : ''}</td>
                  <td className="text-right">{Number(line.credit) ? `Rs ${formatMoney(line.credit)}` : ''}</td>
                  <td className="text-right font-medium">Rs {formatMoney(line.balance)}</td>
                </tr>
              ))}
              <tr><td colSpan={5} className="font-semibold">Closing balance</td><td className="text-right font-semibold">Rs {formatMoney(ledger.closing_balance)}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {aged && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <AgedCard title="Aged Receivables" rows={aged.receivables} />
          <AgedCard title="Aged Payables" rows={aged.payables} />
        </div>
      )}
      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr><th>Name</th><th>Type</th><th className="text-right">Balance</th><th></th></tr>
          </thead>
          <tbody>
            {parties.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td><span className="badge bg-slate-100 text-slate-600">{p.party_type}</span></td>
                <td className="text-right font-medium">Rs {formatMoney(p.balance)}</td>
                <td className="text-right">
                  <button className="btn-secondary no-print" onClick={() => openLedger(p)}>View ledger</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function AgedCard({ title, rows }: { title: string; rows: AgedRow[] }) {
  const buckets: AgedRow['bucket'][] = ['0-30', '31-60', '61-90', '90+']
  return (
    <div className="card p-4">
      <h3 className="font-medium mb-3">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-slate-400">Nothing outstanding.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr><th>Party</th>{buckets.map((b) => <th key={b} className="text-right">{b}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.party_id}>
                <td>{r.party_name}</td>
                {buckets.map((b) => (
                  <td key={b} className="text-right">{r.bucket === b ? `Rs ${formatMoney(r.balance)}` : ''}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// -- Vouchers ----------------------------------------------------------------

function VouchersTab() {
  const [vouchers, setVouchers] = useState<Voucher[]>([])
  const [accounts, setAccounts] = useState<ChartOfAccount[]>([])
  const [parties, setParties] = useState<Party[]>([])
  const [showForm, setShowForm] = useState(false)
  const [voucherType, setVoucherType] = useState<Voucher['voucher_type']>('EXPENSE')
  const [narration, setNarration] = useState('')
  const [amount, setAmount] = useState('')
  const [paymentMode, setPaymentMode] = useState<'CASH' | 'BANK'>('CASH')
  const [debitAccount, setDebitAccount] = useState('')
  const [party, setParty] = useState('')
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)

  function loadVouchers() {
    api.get<Paginated<Voucher> | Voucher[]>('accounting/vouchers/', { params: { page_size: 100 } })
      .then((res) => setVouchers(Array.isArray(res.data) ? res.data : res.data.results))
  }

  useEffect(() => {
    loadVouchers()
    api.get<Paginated<ChartOfAccount> | ChartOfAccount[]>('accounting/chart-of-accounts/', { params: { page_size: 100 } })
      .then((res) => setAccounts(Array.isArray(res.data) ? res.data : res.data.results))
    api.get<Paginated<Party> | Party[]>('accounting/parties/', { params: { page_size: 500 } })
      .then((res) => setParties(Array.isArray(res.data) ? res.data : res.data.results))
  }, [])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      await api.post('accounting/vouchers/', {
        voucher_type: voucherType,
        narration,
        amount: amount || null,
        payment_mode: voucherType === 'JOURNAL' ? '' : paymentMode,
        debit_account: debitAccount ? Number(debitAccount) : null,
        party: party ? Number(party) : null,
      })
      setShowForm(false)
      setNarration(''); setAmount(''); setDebitAccount(''); setParty('')
      loadVouchers()
    } catch (err: any) {
      setError(err?.response?.data ? JSON.stringify(err.response.data) : 'Could not create voucher.')
    }
  }

  async function postVoucher(v: Voucher) {
    setBusyId(v.id)
    try {
      await api.post(`accounting/vouchers/${v.id}/post_voucher/`)
      loadVouchers()
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Could not post voucher.')
    } finally {
      setBusyId(null)
    }
  }

  const expenseAccounts = accounts.filter((a) => a.account_type === 'EXPENSE')
  const payableAccounts = accounts.filter((a) => ['LIABILITY', 'ASSET'].includes(a.account_type))

  return (
    <div className="space-y-6">
      <div className="flex justify-end no-print">
        <button className="btn-primary" onClick={() => setShowForm((s) => !s)}>
          {showForm ? 'Cancel' : '+ New Voucher'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="card p-4 space-y-4 no-print">
          <div className="grid grid-cols-3 gap-3">
            <select className="input" value={voucherType} onChange={(e) => setVoucherType(e.target.value as Voucher['voucher_type'])}>
              {VOUCHER_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <input className="input" placeholder="Narration" value={narration} onChange={(e) => setNarration(e.target.value)} required />
            {voucherType !== 'JOURNAL' && (
              <input className="input" type="number" step="0.01" placeholder="Amount" value={amount} onChange={(e) => setAmount(e.target.value)} required />
            )}
          </div>
          {voucherType !== 'JOURNAL' && (
            <div className="grid grid-cols-3 gap-3">
              <select className="input" value={paymentMode} onChange={(e) => setPaymentMode(e.target.value as 'CASH' | 'BANK')}>
                <option value="CASH">Cash</option>
                <option value="BANK">Bank</option>
              </select>
              <select className="input" value={debitAccount} onChange={(e) => setDebitAccount(e.target.value)} required>
                <option value="">{voucherType === 'EXPENSE' ? 'Expense account...' : 'Payable/debit account...'}</option>
                {(voucherType === 'EXPENSE' ? expenseAccounts : payableAccounts).map((a) => (
                  <option key={a.id} value={a.id}>{a.code} - {a.name}</option>
                ))}
              </select>
              <select className="input" value={party} onChange={(e) => setParty(e.target.value)}>
                <option value="">No party</option>
                {parties.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          )}
          <p className="text-xs text-slate-400">Journal vouchers with custom line items can be entered from /admin/ for now.</p>
          <button type="submit" className="btn-primary">Save Voucher</button>
          {error && <div className="text-sm text-red-600">{error}</div>}
        </form>
      )}

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr><th>Voucher #</th><th>Type</th><th>Date</th><th>Narration</th><th className="text-right">Amount</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {vouchers.length === 0 ? (
              <tr><td colSpan={7} className="text-center text-slate-400 py-6">No vouchers yet.</td></tr>
            ) : vouchers.map((v) => (
              <tr key={v.id}>
                <td className="font-mono text-xs">{v.voucher_number}</td>
                <td>{v.voucher_type}</td>
                <td>{v.date}</td>
                <td>{v.narration}</td>
                <td className="text-right">{v.amount ? `Rs ${formatMoney(v.amount)}` : '—'}</td>
                <td>
                  <span className={`badge ${v.status === 'POSTED' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'}`}>{v.status}</span>
                </td>
                <td className="text-right">
                  {v.status === 'DRAFT' && (
                    <button className="btn-secondary no-print" disabled={busyId === v.id} onClick={() => postVoucher(v)}>Post</button>
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

// -- Financial Statements ----------------------------------------------------

function StatementsTab() {
  const [sub, setSub] = useState<'income' | 'balance' | 'cashflow'>('income')
  const today = new Date().toISOString().slice(0, 10)
  const monthStart = today.slice(0, 8) + '01'
  const [dateFrom, setDateFrom] = useState(monthStart)
  const [dateTo, setDateTo] = useState(today)
  const [asOf, setAsOf] = useState(today)
  const [income, setIncome] = useState<IncomeStatement | null>(null)
  const [balance, setBalance] = useState<BalanceSheet | null>(null)
  const [cashflow, setCashflow] = useState<CashflowStatement | null>(null)

  useEffect(() => {
    if (sub === 'income') {
      api.get<IncomeStatement>('accounting/statements/income_statement/', { params: { date_from: dateFrom, date_to: dateTo } }).then((r) => setIncome(r.data))
    } else if (sub === 'balance') {
      api.get<BalanceSheet>('accounting/statements/balance_sheet/', { params: { as_of: asOf } }).then((r) => setBalance(r.data))
    } else {
      api.get<CashflowStatement>('accounting/statements/cashflow_statement/', { params: { date_from: dateFrom, date_to: dateTo } }).then((r) => setCashflow(r.data))
    }
  }, [sub, dateFrom, dateTo, asOf])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between no-print">
        <div className="flex gap-2">
          {(['income', 'balance', 'cashflow'] as const).map((s) => (
            <button key={s} className={sub === s ? 'btn-primary' : 'btn-secondary'} onClick={() => setSub(s)}>
              {s === 'income' ? 'Income Statement' : s === 'balance' ? 'Balance Sheet' : 'Cashflow'}
            </button>
          ))}
        </div>
        <button className="btn-secondary" onClick={() => window.print()}>Print</button>
      </div>

      <div className="flex gap-3 no-print">
        {sub === 'balance' ? (
          <input className="input max-w-xs" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        ) : (
          <>
            <input className="input max-w-xs" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            <input className="input max-w-xs" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </>
        )}
      </div>

      {sub === 'income' && income && (
        <div className="card p-4 space-y-4">
          <h2 className="font-medium">Income Statement: {income.date_from} to {income.date_to}</h2>
          <StatementSection title="Income" rows={income.income} total={income.total_income} />
          <StatementSection title="Expenses" rows={income.expenses} total={income.total_expenses} />
          <div className="flex justify-between border-t pt-3 font-semibold">
            <span>Net Income</span><span>Rs {formatMoney(income.net_income)}</span>
          </div>
        </div>
      )}

      {sub === 'balance' && balance && (
        <div className="card p-4 space-y-4">
          <h2 className="font-medium">Balance Sheet as of {balance.as_of}</h2>
          <StatementSection title="Assets" rows={balance.assets} total={balance.total_assets} />
          <StatementSection title="Liabilities" rows={balance.liabilities} total={balance.total_liabilities} />
          <StatementSection title="Equity" rows={balance.equity} total={balance.total_equity} />
        </div>
      )}

      {sub === 'cashflow' && cashflow && (
        <div className="card p-4 space-y-4">
          <h2 className="font-medium">Cashflow Statement: {cashflow.date_from} to {cashflow.date_to}</h2>
          <div className="flex justify-between"><span>Opening cash</span><span>Rs {formatMoney(cashflow.opening_cash)}</span></div>
          <div className="flex justify-between"><span>Total inflows</span><span>Rs {formatMoney(cashflow.total_inflows)}</span></div>
          <div className="flex justify-between"><span>Total outflows</span><span>Rs {formatMoney(cashflow.total_outflows)}</span></div>
          <div className="flex justify-between border-t pt-3 font-semibold"><span>Closing cash</span><span>Rs {formatMoney(cashflow.closing_cash)}</span></div>
        </div>
      )}
    </div>
  )
}

function StatementSection({ title, rows, total }: { title: string; rows: { code: string; name: string; amount: string }[]; total: string }) {
  return (
    <div>
      <h3 className="text-sm font-medium text-slate-500 mb-2">{title}</h3>
      <table className="data-table">
        <tbody>
          {rows.length === 0 ? (
            <tr><td className="text-slate-400">None</td></tr>
          ) : rows.map((r) => (
            <tr key={r.code}><td>{r.name}</td><td className="text-right">Rs {formatMoney(r.amount)}</td></tr>
          ))}
          <tr className="font-semibold"><td>Total {title}</td><td className="text-right">Rs {formatMoney(total)}</td></tr>
        </tbody>
      </table>
    </div>
  )
}
