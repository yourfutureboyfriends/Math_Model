// Shared display formatters for panels. Missing or non-finite values show as "—".
const bad = (v: number | null | undefined): v is null | undefined => v == null || !Number.isFinite(v);

/** A fraction as a percentage: 0.1234 → "12.3%". */
export const pct = (v: number | null | undefined, d = 1): string => (bad(v) ? '—' : `${(v * 100).toFixed(d)}%`);

/** A fraction as a signed percentage: 0.05 → "+5.0%", −0.05 → "-5.0%". */
export const signedPct = (v: number | null | undefined, d = 1): string =>
  (bad(v) ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);

/** A number with up to `d` decimals and thousands separators. */
export const num = (v?: number | null, d = 2): string =>
  (bad(v) ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: d }));
