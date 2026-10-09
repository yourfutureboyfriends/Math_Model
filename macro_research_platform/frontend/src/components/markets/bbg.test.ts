import { describe, expect, it } from 'vitest';
import { fromTerminal, toTerminal } from './bbg';
import { parseCommand } from './functions';

describe('terminal identifiers', () => {
  it('parses securities', () => {
    expect(fromTerminal('AAPL US Equity')).toBe('AAPL');
    expect(fromTerminal('VOD LN Equity')).toBe('VOD.L');
    expect(fromTerminal('7203 JP Equity')).toBe('7203.T');
    expect(fromTerminal('5 HK Equity')).toBe('0005.HK');
    expect(fromTerminal('SPX Index')).toBe('^GSPC');
    expect(fromTerminal('EURUSD Curncy')).toBe('EURUSD=X');
    expect(fromTerminal('USDJPY Curncy')).toBe('JPY=X');
    expect(fromTerminal('XBTUSD Curncy')).toBe('BTC-USD');
    expect(fromTerminal('CL1 Comdty')).toBe('CL=F');
  });
  it('labels symbols', () => {
    expect(toTerminal('AAPL', 'Stock')).toBe('AAPL US Equity');
    expect(toTerminal('0005.HK')).toBe('5 HK Equity');
    expect(toTerminal('^GSPC')).toBe('SPX Index');
    expect(toTerminal('GC=F')).toBe('GC1 Comdty');
    expect(toTerminal('JPY=X')).toBe('USDJPY Curncy');
  });
  it('parses commands in terminal form', () => {
    expect(parseCommand('AAPL US Equity DES')).toMatchObject({ symbol: 'AAPL', terminal: true, fn: { code: 'DES' } });
    expect(parseCommand('VOD LN GP')).toMatchObject({ symbol: 'VOD.L', fn: { code: 'GP' } });
    expect(parseCommand('SPX Index')).toMatchObject({ symbol: '^GSPC', terminal: true });
    expect(parseCommand('NVDA OMON')).toMatchObject({ symbol: 'NVDA', fn: { code: 'OMON' } });
    expect(parseCommand('WEI').fn?.code).toBe('WEI');
  });
});
