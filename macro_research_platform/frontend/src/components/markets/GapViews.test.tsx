import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import fx from './StandardViews.fixtures.json';
import { BorrowCard, BorrowView, CrprView, DarkView, LeagView, ProbView, SpfPanel } from './GapViews';

// Responses captured from the live endpoints (BORROW, DARK/PROB TSLA, CRPR MSFT, LEAG, SPF), trimmed.
const mock = vi.hoisted(() => ({ urls: [] as string[] }));
vi.mock('./shared', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./shared')>()),
  useJSON: (url: string | null) => {
    if (url) mock.urls.push(url);
    const m = url?.match(/\/mkt\/(borrow|dark|prob|crpr|leag|spf)(\/[^?]+)?/);
    const key = (m ? (m[1] === 'borrow' && m[2] ? 'borrowone' : m[1]) : undefined) as keyof typeof fx | undefined;
    return { data: key ? fx[key] : null, error: null, loading: false };
  },
}));
vi.mock('@/components/ui/LineChart', () => ({ LineChart: ({ lines }: { lines: { label: string }[] }) => <div data-chart>{lines.map((l) => l.label).join('|')}</div> }));

let host: HTMLDivElement, root: ReturnType<typeof createRoot>;
beforeEach(() => { vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true); localStorage.clear(); mock.urls = []; host = document.createElement('div'); document.body.append(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); localStorage.clear(); vi.unstubAllGlobals(); });
const click = (text: string) => act(() => { Array.from(host.querySelectorAll('button')).find((b) => b.textContent?.startsWith(text))!.click(); });

it('BORROW lists the costliest names and remembers the chosen list', async () => {
  await act(async () => root.render(<BorrowView onOpen={() => {}} />));
  expect(host.querySelector('tbody')!.textContent).toContain(fx.borrow.hardest[0].symbol);
  click('S&P 500');
  expect(host.querySelector('tbody')!.textContent).toContain(fx.borrow.index_members[0].symbol);
  expect(localStorage.getItem('view.borrow.tab')).toBe('"index"');
});

it('the borrow card shows the fee and tier', async () => {
  await act(async () => root.render(<BorrowCard symbol="TSLA" />));
  expect(host.textContent).toContain('Cost to borrow');
  expect(host.textContent).toContain(fx.borrowone.tier);
});

it('DARK shows the off-exchange share and venues', async () => {
  await act(async () => root.render(<DarkView symbol="TSLA" />));
  expect(host.textContent).toContain(fx.dark.venues[0].venue);
  expect(host.textContent).toContain(`week of ${fx.dark.latest_week}`);
});

it('PROB answers the probability of any typed level', async () => {
  await act(async () => root.render(<ProbView symbol="TSLA" />));
  expect(host.textContent).toContain('Chance it finishes higher');
  const input = host.querySelector<HTMLInputElement>('[aria-label="Price level"]')!;
  act(() => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, String(fx.prob.spot)); input.dispatchEvent(new Event('input', { bubbles: true })); });
  expect(host.textContent).toMatch(/% above · .*% below/);
});

it('CRPR shows the synthetic rating and Piotroski tests', async () => {
  await act(async () => root.render(<CrprView symbol="MSFT" />));
  expect(host.textContent).toContain(fx.crpr.synthetic_rating);
  expect(host.textContent).toContain('Piotroski tests');
});

it('LEAG ranks banks and switches the company list', async () => {
  await act(async () => root.render(<LeagView onGo={() => {}} />));
  expect(host.textContent).toContain(`${fx.leag.rows[0].bank}: companies advised`);
  click(fx.leag.rows[1].bank);
  expect(host.textContent).toContain(`${fx.leag.rows[1].bank}: companies advised`);
});

it('SPF shows the survey with changes since the last one', async () => {
  await act(async () => root.render(<SpfPanel />));
  expect(host.textContent).toContain(`Survey of Professional Forecasters, ${fx.spf.survey}`);
  expect(host.textContent).toContain('10-year Treasury yield');
});
