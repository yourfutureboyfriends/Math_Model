import { describe, expect, it } from 'vitest';
import { EXCHANGES, sessionState } from './MarketClock';

const ex = (code: string) => EXCHANGES.find((e) => e.code === code)!;

describe('sessionState', () => {
  it('knows an open session and the time to close', () => {
    const s = sessionState(ex('NYSE'), new Date('2026-10-09T14:00:00Z'));      // Fri 10:00 New York
    expect(s.state).toBe('open');
    expect(s.next).toBe('closes in 6h 0m');
  });
  it('treats the gap between sessions as lunch', () => {
    expect(sessionState(ex('HKEX'), new Date('2026-10-09T04:30:00Z')).state).toBe('lunch');   // 12:30 Hong Kong
  });
  it('counts to Monday over the weekend', () => {
    const s = sessionState(ex('TSE'), new Date('2026-10-10T03:00:00Z'));       // Sat 12:00 Tokyo
    expect(s.state).toBe('closed');
    expect(s.next).toBe('opens in 1d 21h');
  });
  it('trades Sunday in Riyadh', () => {
    expect(sessionState(ex('TADAWUL'), new Date('2026-10-11T08:00:00Z')).state).toBe('open');   // Sun 11:00 Riyadh
  });
});
