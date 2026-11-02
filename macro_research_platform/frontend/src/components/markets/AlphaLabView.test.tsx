import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import fx from './AlphaLab.fixtures.json';
import { AlphaLabView, ProofView } from './AlphaLabView';

// Trimmed real outputs of the Stock Signal Lab and the what-works scorecard.
const mock = vi.hoisted(() => ({ state: 'ready' as 'ready' | 'computing' }));
vi.mock('./shared', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./shared')>()),
  useJSON: (url: string | null) => ({
    data: url?.includes('/proof') ? fx.proof : mock.state === 'computing' ? { status: 'computing', started_seconds_ago: 42, note: 'building' } : fx.alphalab,
    error: null, loading: false,
  }),
}));
vi.mock('@/components/ui/LineChart', () => ({ LineChart: () => <div data-chart /> }));

let host: HTMLDivElement, root: ReturnType<typeof createRoot>;
beforeEach(() => { vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true); mock.state = 'ready'; host = document.createElement('div'); document.body.append(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); });

it('ALPHA states the verdict plainly and lists every signal and both composites', async () => {
  await act(async () => root.render(<AlphaLabView onOpen={() => {}} />));
  expect(host.querySelector('.alpha-verdict')?.textContent).toContain(fx.alphalab.edge.level === 'none' ? 'No reliable edge' : '');
  for (const s of fx.alphalab.signals) expect(host.textContent).toContain(s.name);
  for (const c of fx.alphalab.composites) expect(host.textContent).toContain(c.name);
  act(() => { Array.from(host.querySelectorAll('button')).find((b) => b.textContent === 'Short book')!.click(); });
  expect(host.textContent).toContain('Borrow');
});

it('ALPHA shows build progress instead of an empty page', async () => {
  mock.state = 'computing';
  await act(async () => root.render(<AlphaLabView onOpen={() => {}} />));
  expect(host.textContent).toContain('42s so far');
});

it('PROOF ranks by verdict and filters', async () => {
  await act(async () => root.render(<ProofView onGo={() => {}} />));
  expect(host.textContent).toContain(fx.proof.headline);
  act(() => { Array.from(host.querySelectorAll('button')).find((b) => b.textContent?.startsWith('Promising'))!.click(); });
  const pills = Array.from(host.querySelectorAll('tbody .proof-pill')).map((p) => p.textContent);
  expect(pills.length).toBeGreaterThan(0);
  expect(pills.every((p) => p === 'Promising')).toBe(true);
});
