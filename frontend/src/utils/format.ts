export function formatMoney(value: string | number | null | undefined): string {
  const num = Number(value ?? 0)
  return new Intl.NumberFormat('en-PK', { maximumFractionDigits: 0 }).format(num)
}

export function formatNumber(value: string | number | null | undefined): string {
  const num = Number(value ?? 0)
  return new Intl.NumberFormat('en-PK').format(num)
}

/** Volume in M's (1,000 sticks), PTC's own reporting unit. */
export function formatM(value: string | number | null | undefined): string {
  const num = Number(value ?? 0)
  return `${new Intl.NumberFormat('en-PK', { maximumFractionDigits: 1 }).format(num)} M`
}

/** Compact rupees for headline figures: Rs 62.1 Cr / Rs 4.2 Lac. */
export function formatRsShort(value: string | number | null | undefined): string {
  const num = Number(value ?? 0)
  const abs = Math.abs(num)
  if (abs >= 1e7) return `Rs ${(num / 1e7).toFixed(2)} Cr`
  if (abs >= 1e5) return `Rs ${(num / 1e5).toFixed(1)} Lac`
  return `Rs ${formatMoney(num)}`
}
