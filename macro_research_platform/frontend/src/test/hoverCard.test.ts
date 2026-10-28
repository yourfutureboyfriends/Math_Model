import { describe, expect, it } from 'vitest';
import { symbolOf } from '@/components/layout/HoverCard';

const cell = (text: string, opts: { mono?: boolean; inPanel?: boolean } = {}) => {
  const panel = document.createElement('div');
  if (opts.inPanel !== false) panel.className = 'terminal-section';
  const td = document.createElement('span');
  if (opts.mono !== false) td.className = 'font-mono';
  td.textContent = text;
  panel.appendChild(td);
  document.body.appendChild(panel);
  return td;
};

describe('hover-card ticker detection', () => {
  it('recognises tickers in panel cells', () => {
    for (const t of ['SPY', 'CSPX.L', 'EURUSD=X', '^N225', 'BTC-USD', '7203.T', 'BRK-B']) expect(symbolOf(cell(t))).toBe(t);
  });

  it('ignores table words, periods, regions, country codes, numbers and long words', () => {
    for (const t of ['BUY', 'USD', 'OK', '1M', '3Y', 'US', 'EA', 'DE', 'CL', '19.6K', '200K', 'REFLATION', 'BULLISH', 'U', '2024'])
      expect(symbolOf(cell(t))).toBeNull();
  });

  it('only guesses inside panels and monospace cells; data-symbol always wins', () => {
    expect(symbolOf(cell('SPY', { inPanel: false }))).toBeNull();
    expect(symbolOf(cell('SPY', { mono: false }))).toBeNull();
    const b = document.createElement('button');
    b.setAttribute('data-symbol', '^gspc');
    b.innerHTML = '<span>SPX</span>';
    document.body.appendChild(b);
    expect(symbolOf(b.firstElementChild)).toBe('^GSPC');
  });
});
