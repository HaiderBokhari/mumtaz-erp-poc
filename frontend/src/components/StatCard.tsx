interface StatCardProps {
  label: string
  value: string
  hint?: string
  tone?: 'default' | 'warning' | 'good'
}

const TONE_CLASSES: Record<NonNullable<StatCardProps['tone']>, string> = {
  default: 'text-slate-900',
  warning: 'text-amber-600',
  good: 'text-emerald-600',
}

export default function StatCard({ label, value, hint, tone = 'default' }: StatCardProps) {
  return (
    <div className="card p-4">
      <div className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${TONE_CLASSES[tone]}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  )
}
