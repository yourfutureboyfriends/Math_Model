import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import fx from './StandardViews.fixtures.json';
import { CdsaView, CdsxView, ExthView, SwapView, TranView } from './FreeDataViews';

// Responses captured from the live endpoints (SWAP, CDSX, CDSA, EXTH, TRAN MSFT), trimmed.
const mock = vi.hoisted(() => ({ urls: [] as string[] }));
vi.mock('./shared', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./shared')>()),
  useJSON: (url: string | null) => {
    if (url) mock.urls.push(url);
    const key = url?.includes('/search?') ? 'transearch' : url?.includes('/call/') ? null : url?.match(/\/mkt\/(swap|cdsx|cdsa|exth|tran)\b/)?.[1];
    return { data: key ? (fx as any)[key] : null, error: null, loading: false };
  },
}));
vi.mock('@/components/ui/LineChart', () => ({ LineChart: ({ lines }: { lines: { label: string }[] }) => <div data-chart>{lines.map((l) => l.label).join('|')}</div> }));

let host: HTMLDivElement, root: ReturnType<typeof createRoot>;
beforeEach(() => { vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true); localStorage.clear(); mock.urls = []; host = document.createElement('div'); document.body.append(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); localStorage.clear(); vi.unstubAllGlobals(); });
const click = (text: string) => act(() => { Array.from(host.querySelectorAll('button')).find((b) => b.textContent?.startsWith(text))!.click(); });

it('SWAP tabulates every curve and charts the chosen one', async () => {
  await act(async () => root.render(<SwapView />));
  expect(host.textContent).toContain(`trades reported on ${fx.swap.date}`);
  const rows = host.querySelectorAll('tbody tr');
  act(() => (rows[1] as HTMLElement).click());
  expect(host.textContent).toContain(`${fx.swap.curves[1].name}: curve`);
  expect(localStorage.getItem('view.swap.code')).toBe(JSON.stringify(fx.swap.curves[1].code));
});

it('CDSX shows index levels with credit-direction colours', async () => {
  await act(async () => root.render(<CdsxView />));
  expect(host.textContent).toContain(fx.cdsx.rows[0].name);
  expect(host.textContent).toMatch(/≈\d+ bp/);                         // HY's price shown with a spread equivalent
});

it('CDSA filters to sovereigns', async () => {
  await act(async () => root.render(<CdsaView onOpen={() => {}} />));
  click('Sovereigns');
  const types = Array.from(host.querySelectorAll('tbody tr td:nth-child(3)')).map((td) => td.textContent);
  expect(types.every((t) => t === 'Sovereign')).toBe(true);
});

it('EXTH switches session and size filter', async () => {
  await act(async () => root.render(<ExthView onOpen={() => {}} />));
  expect(host.textContent).toContain('Biggest gainers');
  click('After hours');
  click('Over $10B');
  expect(mock.urls.at(-1)).toContain('session=AFTER_MARKET');
  expect(mock.urls.at(-1)).toContain('min_cap=10000000000');
});

it('TRAN shows the latest call and searches across calls', async () => {
  await act(async () => root.render(<TranView symbol="MSFT" />));
  expect(host.textContent).toContain(`MSFT earnings call — ${fx.tran.latest.date}`);
  const input = host.querySelector<HTMLInputElement>('[aria-label="Search calls"]')!;
  act(() => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, 'azure growth'); input.dispatchEvent(new Event('input', { bubbles: true })); });
  act(() => { input.form!.requestSubmit(); });
  expect(mock.urls.at(-1)).toContain('/search?q=azure%20growth');
  expect(host.querySelectorAll('mark').length).toBeGreaterThan(0);
});
