interface MonthPickerProps {
  months: string[]
  value: string
  onChange: (month: string) => void
}

function monthLabel(month: string) {
  const [y, m] = month.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleString('en-GB', { month: 'long', year: 'numeric' })
}

export default function MonthPicker({ months, value, onChange }: MonthPickerProps) {
  return (
    <select className="input w-auto no-print" value={value} onChange={(e) => onChange(e.target.value)}>
      {months.map((m) => (
        <option key={m} value={m}>{monthLabel(m)}</option>
      ))}
    </select>
  )
}

export { monthLabel }
