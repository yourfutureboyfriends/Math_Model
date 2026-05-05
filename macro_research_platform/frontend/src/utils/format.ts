// Safe number formatting utilities
// Prevents NaN/Infinity from displaying in the UI

export function safeNum(v: number | null | undefined, decimals = 2, suffix = ''): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v) || !isFinite(v)) return '—';
  return v.toFixed(decimals) + suffix;
}

export function safePct(v: number | null | undefined, decimals = 1): string {
  return safeNum(v, decimals, '%');
}

export function clampPct(v: number | null | undefined): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v)) return '—';
  return `${Math.min(100, Math.max(0, Math.round(v)))}%`;
}

export function safeSign(v: number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v) || !isFinite(v)) return '—';
  return (v >= 0 ? '+' : '') + v.toFixed(decimals);
}

export function safeBps(v: number | null | undefined): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v)) return '—';
  return `${Math.round(v)} bps`;
}

export function safeInt(v: number | null | undefined): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v) || !isFinite(v)) return '—';
  return Math.round(v).toString();
}

export function safeCurrency(v: number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v) || !isFinite(v)) return '—';
  return '$' + v.toFixed(decimals);
}

export function safeRatio(v: number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v) || !isFinite(v)) return '—';
  return v.toFixed(decimals) + 'x';
}
