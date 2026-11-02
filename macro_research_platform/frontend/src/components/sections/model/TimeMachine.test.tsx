import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { TimeMachine } from './TimeMachine';

const REG = ['Goldilocks', 'Reflation', 'Stagflation', 'Deflationary slowdown'];
const rows = Array.from({ length: 36 }, (_, k) => {
  const m = new Date(Date.UTC(2007, k, 15)).toISOString().slice(0, 7);
  const top = REG[Math.floor(k / 9) % 4];
  return { decided: m, month: m, growth: Math.sin(k / 5), inflation: Math.cos(k / 6), top, p_g: 0.6, p_i: 0.4, cash: 0.1,
           probs: Object.fromEntries(REG.map((q) => [q, q === top ? 0.55 : 0.15])), weights: { Equities: 0.5 + k / 200, Bonds: 0.4 - k / 200 },
           realised: k < 24 ? REG[Math.floor((k + 3) / 9) % 4] : null, next_12m: k < 24 ? { model: 0.05, strategic: 0.03, sixty_forty: -0.02 } : undefined };
});

let host: HTMLDivElement, root: ReturnType<typeof createRoot>;
beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  host = document.createElement('div'); document.body.append(host); root = createRoot(host);
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => 600 });
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); delete (HTMLElement.prototype as any).clientWidth; });

it('opens on the latest month with its regime, ribbon and quadrant drawn', async () => {
  await act(async () => root.render(<TimeMachine timeline={rows} />));
  expect(host.textContent).toContain(new Date('2009-12-15').toLocaleDateString(undefined, { month: 'long', year: 'numeric' }));
  expect(host.querySelector('.tm-pill')!.textContent).toContain(rows[35].top);
  expect(host.querySelectorAll('.tm-ribbon rect').length).toBeGreaterThanOrEqual(36);   // one regime cell per month
  expect(host.textContent).toContain('Not 12 months yet.');
});

it('steps with the keyboard and jumps to an event', async () => {
  await act(async () => root.render(<TimeMachine timeline={rows} />));
  const tm = host.querySelector<HTMLElement>('.tm-root')!;
  act(() => { tm.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', shiftKey: true, bubbles: true })); });
  expect(host.textContent).toContain(new Date('2008-12-15').toLocaleDateString(undefined, { month: 'long', year: 'numeric' }));
  act(() => { Array.from(host.querySelectorAll('button')).find((b) => b.textContent === 'Lehman')!.click(); });
  expect(host.textContent).toContain(new Date('2008-09-15').toLocaleDateString(undefined, { month: 'long', year: 'numeric' }));
  expect(host.querySelector('.tm-hindsight')).not.toBeNull();
  expect(host.textContent).toContain('Tactical');
});

it('explains an empty timeline', async () => {
  await act(async () => root.render(<TimeMachine timeline={[]} />));
  expect(host.textContent).toContain("model's next full run");
});
