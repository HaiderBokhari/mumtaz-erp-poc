export function formatMoney(value: string | number | null | undefined): string {
  const num = Number(value ?? 0)
  return new Intl.NumberFormat('en-PK', { maximumFractionDigits: 0 }).format(num)
}

export function formatNumber(value: string | number | null | undefined): string {
  const num = Number(value ?? 0)
  return new Intl.NumberFormat('en-PK').format(num)
}
