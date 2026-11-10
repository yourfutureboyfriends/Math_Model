// The fund's base currency (GBP for Moriah). The book, P&L, VaR and attribution are valued in it by the backend, so
// panels format those amounts with it instead of a hard-coded "$". Read once from the fund settings; panels that use
// the hook re-render when it arrives.
import { useEffect, useState } from 'react';

let base = 'USD';
let started = false;
const subs = new Set<() => void>();

export function baseCurrency(): string {
  if (!started) {
    started = true;
    fetch('/api/v1/fund/settings')
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        const c = typeof j?.base_currency === 'string' ? j.base_currency.toUpperCase() : null;
        if (c && c !== base) { base = c; subs.forEach((f) => f()); }
      })
      .catch(() => { started = false; });            // try again on the next use
  }
  return base;
}

export function useBaseCurrency(): string {
  const [, force] = useState(0);
  useEffect(() => {
    const f = () => force((n) => n + 1);
    subs.add(f);
    baseCurrency();
    return () => { subs.delete(f); };
  }, []);
  return base;
}

/** An amount in the base currency: "$1,234" for USD, "GBP 1,234" otherwise. */
export function baseMoney(v: number | null | undefined, dp = 0): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const s = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
  return `${v < 0 ? '-' : ''}${base === 'USD' ? '$' : `${base} `}${s}`;
}
