import { describe, expect, it } from 'vitest';
import { cellNumber, columnKind, sortByHeader } from './sortableTables';

describe('cellNumber reads numbers the way tables print them', () => {
  it.each([
    ['1,234.5', 1234.5], ['$1.2B', 1.2e9], ['-3.4%', -3.4], ['(12)', -12], ['25bp', 25], ['8.5×', 8.5],
    ['+0.7', 0.7], ['−2.1%', -2.1], ['€40m', 4e7], ['1.1tn', 1.1e12],
  ])('%s → %d', (s, v) => expect(cellNumber(s)).toBeCloseTo(v));
  it.each(['—', '', 'n/a', 'AAPL', '2026-10-01', 'Q3 2026'])('%s is not a number', (s) => expect(cellNumber(s)).toBeNull());
});

it('a column is numeric when most filled cells are numbers', () => {
  expect(columnKind(['1.2%', '—', '3.4%', '-0.5%'])).toBe('num');
  expect(columnKind(['AAPL', 'MSFT', '12'])).toBe('text');
});

function table(rows: string[][], head = ['Name', 'Chg %']) {
  document.body.innerHTML = `<table><thead><tr>${head.map((h) => `<th>${h}</th>`).join('')}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  const ths = document.querySelectorAll('th');
  const col = (i: number) => [...document.querySelectorAll('tbody tr')].map((r) => (r as HTMLTableRowElement).cells[i].textContent);
  return { ths, col };
}

describe('sortByHeader', () => {
  it('numbers sort high first, then low first, then back to the original order; blanks stay last', () => {
    const { ths, col } = table([['A', '1.0%'], ['B', '—'], ['C', '-2.0%'], ['D', '3.0%']]);
    sortByHeader(ths[1] as HTMLTableCellElement);
    expect(col(0)).toEqual(['D', 'A', 'C', 'B']);
    expect(ths[1].getAttribute('aria-sort')).toBe('descending');
    sortByHeader(ths[1] as HTMLTableCellElement);
    expect(col(0)).toEqual(['C', 'A', 'D', 'B']);
    sortByHeader(ths[1] as HTMLTableCellElement);
    expect(col(0)).toEqual(['A', 'B', 'C', 'D']);
    expect(ths[1].hasAttribute('aria-sort')).toBe(false);
  });

  it('text sorts A→Z first, naturally', () => {
    const { ths, col } = table([['Fund 10', '1'], ['fund 2', '2'], ['Alpha', '3']]);
    sortByHeader(ths[0] as HTMLTableCellElement);
    expect(col(0)).toEqual(['Alpha', 'fund 2', 'Fund 10']);
  });

  it('leaves tables with merged cells alone', () => {
    const { ths, col } = table([['A', '1'], ['B', '4'], ['C', '3'], ['D', '2']]);
    document.querySelector('tbody tr:nth-child(2)')!.innerHTML = '<td colspan="2">Subtotal</td>';
    sortByHeader(ths[1] as HTMLTableCellElement);
    expect(col(0)[0]).toBe('A');
    expect(document.querySelector('table')!.dataset.autosort).toBe('off');
  });
});
