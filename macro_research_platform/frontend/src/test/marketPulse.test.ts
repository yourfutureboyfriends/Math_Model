import { describe, expect, it } from 'vitest';
import { fmtPulseChange, fmtPulsePrice, SHORT, STRIP_SYMBOLS, TAPE_SECTIONS } from '@/lib/marketPulse';

describe('world market feed formatting', () => {
  it('quotes yields in % with bp changes, FX to 4 dp, indices without decimals', () => {
    expect(fmtPulsePrice({ symbol: '^TNX', name: 'US 10Y', price: 4.9861, is_yield: true })).toBe('4.986%');
    expect(fmtPulseChange({ symbol: '^TNX', name: 'US 10Y', price: 4.98, is_yield: true, change_1d_bp: -0.2 })).toEqual({ text: '-0.2bp', dir: -1 });
    expect(fmtPulsePrice({ symbol: 'EURUSD=X', name: 'EUR/USD', price: 1.11789 })).toBe('1.1179');
    expect(fmtPulsePrice({ symbol: '^N225', name: 'Nikkei', price: 62693.4 })).toBe('62,693');
    expect(fmtPulseChange({ symbol: '^N225', name: 'Nikkei', price: 1, change_1d: -0.0034 })).toEqual({ text: '-0.34%', dir: -1 });
    expect(fmtPulsePrice({ symbol: 'X', name: 'x', price: null })).toBe('—');
  });

  it('runs the tape with the trading day: Asia-Pacific, then EMEA, then the Americas', () => {
    expect(TAPE_SECTIONS.slice(0, 3).map((s) => s.tag)).toEqual(['ASIA-PAC', 'EMEA', 'AMERICAS']);
  });

  it('has a short code for every symbol shown, and a global top board', () => {
    for (const s of [...STRIP_SYMBOLS, ...TAPE_SECTIONS.flatMap((x) => x.symbols)]) expect(SHORT[s]).toBeTruthy();
    const board = STRIP_SYMBOLS.map((s) => SHORT[s]);
    for (const region of ['SPX', 'SX5E', 'UKX', 'NKY', 'HSI']) expect(board).toContain(region);
  });
});
