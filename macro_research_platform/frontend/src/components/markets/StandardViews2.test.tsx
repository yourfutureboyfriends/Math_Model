import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import fx from './StandardViews.fixtures.json';
import { EaView, EcfcView, EmView, FomcView, FwcvView } from './StandardViews2';

// Responses captured from the live endpoints (FWCV, ECFC, FOMC, EM AAPL, EA SPX), trimmed.
const mock = vi.hoisted(() => ({ urls: [] as string[] }));
vi.mock('./shared', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./shared')>()),
  useJSON: (url: string | null) => {
    if (url) mock.urls.push(url);
    const key = url?.match(/\/mkt\/(fwcv|ecfc|fomc|em|ea)\b/)?.[1] as keyof typeof fx | undefined;
    return { data: key ? fx[key] : null, error: null, loading: false };
  },
}));
vi.mock('@/components/ui/LineChart', () => ({ LineChart: ({ lines }: { lines: { label: string }[] }) => <div data-chart>{lines.map((l) => l.label).join('|')}</div> }));

let host: HTMLDivElement, root: ReturnType<typeof createRoot>;
beforeEach(() => { vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true); mock.urls = []; host = document.createElement('div'); document.body.append(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); });
const click = (text: string) => act(() => { Array.from(host.querySelectorAll('button')).find((b) => b.textContent?.startsWith(text))!.click(); });

it('FWCV tabulates key forwards per market and charts the chosen one', async () => {
  await act(async () => root.render(<FwcvView />));
  expect(host.textContent).toContain('5y5y');
  expect(host.querySelectorAll('tbody tr').length).toBe(fx.fwcv.curves.length);
  act(() => (host.querySelectorAll('tbody tr')[1] as HTMLElement).click());
  expect(host.textContent).toContain(`${fx.fwcv.curves[1].name}: the 1-year rate`);
});

it('ECFC shows IMF forecasts and opens a country page on click', async () => {
  const onGo = vi.fn();
  await act(async () => root.render(<EcfcView onGo={onGo} />));
  expect(host.textContent).toContain(fx.ecfc.rows[0].name);
  act(() => (host.querySelector('tbody tr') as HTMLElement).click());
  expect(onGo).toHaveBeenCalledWith('CTRY', fx.ecfc.rows[0].iso);
});

it('FOMC shows the range, the dots against futures and the decisions', async () => {
  await act(async () => root.render(<FomcView />));
  expect(host.textContent).toContain(`${fx.fomc.target_lower.toFixed(2)}% – ${fx.fomc.target_upper.toFixed(2)}%`);
  expect(host.textContent).toContain('Fed dots vs market pricing');
  expect(host.textContent).toContain(fx.fomc.decisions[0].date);
});

it('EM lays out quarters by fiscal year and switches to revenue', async () => {
  await act(async () => root.render(<EmView symbol="AAPL" />));
  const last = fx.em.rows.at(-1)!;
  expect(host.textContent).toContain(`FY${last.fiscal_year}`);
  click('Revenue');
  expect(host.textContent).toContain('revenue by fiscal quarter');
});

it('EARN summarises the season and requests other indices', async () => {
  await act(async () => root.render(<EaView onOpen={() => {}} />));
  expect(host.textContent).toContain(`${fx.ea.reported} of ${fx.ea.members}`);
  expect(host.textContent).toContain('Biggest share reactions');
  click('NDX');
  expect(mock.urls.at(-1)).toContain('/ea/NDX');
});
