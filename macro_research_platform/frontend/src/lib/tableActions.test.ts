import { afterEach, expect, it, vi } from 'vitest';
import { tableTSV } from './tableData';
import { installTableActions } from './tableActions';

afterEach(() => { document.body.innerHTML = ''; vi.unstubAllGlobals(); });

it('formats a table as tab-separated text that pastes into Excel as columns', () => {
  expect(tableTSV(['Name', 'Value'], [['A\tB', '1.5%'], ['C', '-2']])).toBe('Name\tValue\nA B\t1.5%\nC\t-2');
});

it('shows Copy over a hovered data table and copies it', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal('navigator', { clipboard: { writeText } });
  installTableActions();
  document.body.insertAdjacentHTML('beforeend', '<table><thead><tr><th>Sym</th><th>Chg</th></tr></thead><tbody>'
    + '<tr><td>AAA</td><td>+1%</td></tr><tr><td>BBB</td><td>-2%</td></tr><tr><td>CCC</td><td>0%</td></tr></tbody></table>');
  const table = document.querySelector('table')!;
  table.getBoundingClientRect = () => ({ top: 100, bottom: 300, left: 10, right: 400, height: 200, width: 390, x: 10, y: 100, toJSON: () => ({}) });
  table.querySelector('td')!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
  const bar = document.querySelector<HTMLElement>('.tbl-actions')!;
  expect(bar.hidden).toBe(false);
  bar.querySelector('button')!.click();
  await Promise.resolve();
  expect(writeText).toHaveBeenCalledWith('Sym\tChg\nAAA\t+1%\nBBB\t-2%\nCCC\t0%');
});
