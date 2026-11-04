import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import fx from './StandardViews.fixtures.json';
import { DsView, GeView, MrrView, WbView } from './StandardViews';

// Trimmed responses captured from the live endpoints (MRR SPX YTD, GE AAPL, WB, DS AAPL "share repurchase").
const mock = vi.hoisted(() => ({ urls: [] as string[] }));
vi.mock('./shared', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./shared')>()),
  useJSON: (url: string | null) => {
    if (url) mock.urls.push(url);
    const key = url?.match(/\/mkt\/(mrr|ge|wb|ds)\b/)?.[1] as keyof typeof fx | undefined;
    return { data: key ? fx[key] : null, error: null, loading: false };
  },
}));
vi.mock('@/components/ui/LineChart', () => ({ LineChart: ({ lines }: { lines: { label: string }[] }) => <div data-chart>{lines.map((l) => l.label).join('|')}</div> }));

let host: HTMLDivElement, root: ReturnType<typeof createRoot>;
beforeEach(() => { vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true); mock.urls = []; host = document.createElement('div'); document.body.append(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); });
const click = (text: string) => act(() => { Array.from(host.querySelectorAll('button')).find((b) => b.textContent?.startsWith(text))!.click(); });

it('MRR ranks members, switches period and filters by sector', async () => {
  await act(async () => root.render(<MrrView onOpen={() => {}} />));
  const body = host.querySelector('tbody')!.textContent!;
  expect(body).toContain(fx.mrr.rows[0].symbol);
  expect(host.textContent).toContain(`${fx.mrr.beat_index} of ${fx.mrr.count}`);
  click('1Y');
  expect(mock.urls.at(-1)).toContain('period=1Y');
  const sector = fx.mrr.rows[0].sector as string;
  click(sector);
  expect(Array.from(host.querySelectorAll('tbody tr')).every((tr) => tr.textContent!.includes(sector))).toBe(true);
});

it('GE shows the P/E against its bands and the implied prices', async () => {
  await act(async () => root.render(<GeView symbol="AAPL" />));
  expect(host.textContent).toContain(`${fx.ge.pe!.toFixed(1)}×`);
  expect(host.textContent).toContain(fx.ge.band_prices.mean!.toFixed(2));
  act(() => { Array.from(host.querySelectorAll('button')).find((b) => b.textContent === 'Earnings yield')!.click(); });
  expect(host.textContent).toContain('Earnings yield (EPS ÷ price)');
  expect(host.querySelectorAll('[data-chart]')).toHaveLength(2);
});

it('WB lists yields with spreads and filters by region', async () => {
  await act(async () => root.render(<WbView />));
  expect(host.textContent).toContain('United States');
  click('Europe');
  const names = Array.from(host.querySelectorAll('tbody tr td:first-child')).map((td) => td.textContent);
  expect(names).toContain('Germany');
  expect(names).not.toContain('United States');
});

it('DS searches only after a query and highlights the matched words', async () => {
  await act(async () => root.render(<DsView symbol="AAPL" onGo={() => {}} />));
  expect(mock.urls).toHaveLength(0);
  click('share repurchase');
  expect(mock.urls.at(-1)).toContain('q=share%20repurchase');
  expect(host.querySelectorAll('mark').length).toBeGreaterThan(0);
  expect(host.textContent).toContain('Filings searched');
});
