import { describe, expect, it } from 'vitest';
import { blackScholes, cdf, impliedVol } from './blackScholes';

const base = { spot: 100, strike: 100, years: 1, vol: 0.2, rate: 0.05, div: 0 };

describe('Black–Scholes', () => {
  it('matches the textbook at-the-money values (Hull)', () => {
    expect(blackScholes({ kind: 'call', ...base }).price).toBeCloseTo(10.4506, 3);
    expect(blackScholes({ kind: 'put', ...base }).price).toBeCloseTo(5.5735, 3);
    expect(blackScholes({ kind: 'call', ...base }).delta).toBeCloseTo(0.6368, 3);
  });

  it('satisfies put–call parity with a dividend yield', () => {
    const inp = { ...base, div: 0.03, strike: 110, years: 0.5 };
    const c = blackScholes({ kind: 'call', ...inp }).price, p = blackScholes({ kind: 'put', ...inp }).price;
    expect(c - p).toBeCloseTo(100 * Math.exp(-0.03 * 0.5) - 110 * Math.exp(-0.05 * 0.5), 8);
  });

  it('vega matches a bump of one vol point', () => {
    const up = blackScholes({ kind: 'call', ...base, vol: 0.21 }).price, dn = blackScholes({ kind: 'call', ...base, vol: 0.19 }).price;
    expect(blackScholes({ kind: 'call', ...base }).vega).toBeCloseTo((up - dn) / 2, 3);
  });

  it('falls back to intrinsic value at expiry', () => {
    expect(blackScholes({ kind: 'call', ...base, spot: 120, years: 0 }).price).toBeCloseTo(20);
    expect(blackScholes({ kind: 'put', ...base, spot: 120, years: 0 }).price).toBe(0);
  });

  it('recovers the volatility from a price, and rejects impossible prices', () => {
    const { price } = blackScholes({ kind: 'put', ...base, vol: 0.35 });
    expect(impliedVol(price, { kind: 'put', ...base })).toBeCloseTo(0.35, 5);
    expect(impliedVol(0.0001, { kind: 'call', ...base, strike: 50 })).toBeNull();   // below intrinsic
  });

  it('normal CDF is accurate', () => {
    expect(cdf(0)).toBeCloseTo(0.5, 7);
    expect(cdf(1.96)).toBeCloseTo(0.975, 4);
    expect(cdf(-1.645)).toBeCloseTo(0.05, 3);
  });
});
