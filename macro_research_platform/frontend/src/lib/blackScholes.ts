// Black–Scholes–Merton for European options with a continuous dividend yield: price and the standard Greeks, plus
// implied volatility by bisection. Used by the OVME option calculator. Inputs are annual decimals (0.2 = 20%).

export type OptionKind = 'call' | 'put';
export interface BsInput { kind: OptionKind; spot: number; strike: number; years: number; vol: number; rate: number; div: number }
export interface BsOut { price: number; delta: number; gamma: number; vega: number; theta: number; rho: number; d1: number; d2: number; probItm: number }

const SQRT2PI = Math.sqrt(2 * Math.PI);
export const pdf = (x: number) => Math.exp(-0.5 * x * x) / SQRT2PI;

/** Standard normal CDF (Abramowitz–Stegun 7.1.26 via erf; |error| < 1.5e-7). */
export function cdf(x: number): number {
  const z = Math.abs(x) / Math.SQRT2, t = 1 / (1 + 0.3275911 * z);
  const erf = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-z * z);
  return x >= 0 ? 0.5 * (1 + erf) : 0.5 * (1 - erf);
}

/** Price and Greeks. Vega and rho per 1 percentage point; theta per calendar day. */
export function blackScholes({ kind, spot: S, strike: K, years: T, vol: v, rate: r, div: q }: BsInput): BsOut {
  if (!(S > 0 && K > 0)) throw new Error('Spot and strike must be positive.');
  if (T <= 0 || v <= 0) {                                           // expiry or no volatility: intrinsic value
    const fwd = S * Math.exp(-q * Math.max(T, 0)), df = Math.exp(-r * Math.max(T, 0));
    const itm = kind === 'call' ? fwd > K * df : fwd < K * df;
    const price = Math.max(kind === 'call' ? fwd - K * df : K * df - fwd, 0);
    return { price, delta: itm ? (kind === 'call' ? 1 : -1) : 0, gamma: 0, vega: 0, theta: 0, rho: 0, d1: NaN, d2: NaN, probItm: itm ? 1 : 0 };
  }
  const sq = Math.sqrt(T), d1 = (Math.log(S / K) + (r - q + 0.5 * v * v) * T) / (v * sq), d2 = d1 - v * sq;
  const eq = Math.exp(-q * T), er = Math.exp(-r * T);
  const gamma = eq * pdf(d1) / (S * v * sq), vega = S * eq * pdf(d1) * sq / 100;
  if (kind === 'call') {
    return { price: S * eq * cdf(d1) - K * er * cdf(d2), delta: eq * cdf(d1), gamma, vega, d1, d2, probItm: cdf(d2),
      theta: (-S * eq * pdf(d1) * v / (2 * sq) - r * K * er * cdf(d2) + q * S * eq * cdf(d1)) / 365, rho: K * T * er * cdf(d2) / 100 };
  }
  return { price: K * er * cdf(-d2) - S * eq * cdf(-d1), delta: -eq * cdf(-d1), gamma, vega, d1, d2, probItm: cdf(-d2),
    theta: (-S * eq * pdf(d1) * v / (2 * sq) + r * K * er * cdf(-d2) - q * S * eq * cdf(-d1)) / 365, rho: -K * T * er * cdf(-d2) / 100 };
}

/** The volatility that reproduces a market price, or null when the price is outside the no-arbitrage bounds. */
export function impliedVol(price: number, inp: Omit<BsInput, 'vol'>): number | null {
  let lo = 1e-4, hi = 5;
  const f = (v: number) => blackScholes({ ...inp, vol: v }).price - price;
  if (f(lo) > 0 || f(hi) < 0) return null;
  for (let i = 0; i < 100; i++) { const mid = (lo + hi) / 2; if (f(mid) > 0) hi = mid; else lo = mid; if (hi - lo < 1e-7) break; }
  return (lo + hi) / 2;
}
