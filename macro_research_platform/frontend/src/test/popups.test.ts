import { beforeEach, describe, expect, it, vi } from 'vitest';

const fresh = async () => { vi.resetModules(); return import('@/lib/popups'); };

describe('live pop-ups store', () => {
  beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });

  it('shows a pop-up once, keeps it in the history and counts it as unread', async () => {
    const m = await fresh();
    m.pushPopup({ id: 'a', kind: 'news', title: 'Headline' });
    m.pushPopup({ id: 'a', kind: 'news', title: 'Headline' });            // same id: ignored
    m.pushPopup({ id: 'b', kind: 'move', title: 'SPX ▲ +2.10%', tone: 'up' });
    const s = m.popupState();
    expect(s.toasts.map((t) => t.id)).toEqual(['b', 'a']);
    expect(s.history).toHaveLength(2);
    expect(s.unread).toBe(2);
    m.togglePanel(true);
    expect(m.popupState().unread).toBe(0);
    m.dismissPopup('b');
    expect(m.popupState().toasts.map((t) => t.id)).toEqual(['a']);
  });

  it('keeps at most four toasts on screen', async () => {
    const m = await fresh();
    for (let i = 0; i < 7; i++) m.pushPopup({ id: `n${i}`, kind: 'news', title: `Story ${i}` });
    expect(m.popupState().toasts).toHaveLength(4);
    expect(m.popupState().history).toHaveLength(7);
  });

  it('muting, or switching a kind off, keeps the history but shows no toast — and is remembered', async () => {
    const m = await fresh();
    m.setPopupsEnabled(false);
    m.pushPopup({ id: 'x', kind: 'move', title: 'SPX ▲ +2%' });
    expect(m.popupState().toasts).toHaveLength(0);
    m.setPopupsEnabled(true);
    m.setKindEnabled('eco', false);
    m.pushPopup({ id: 'y', kind: 'eco', title: 'CPI in 10 min' });
    m.pushPopup({ id: 'z', kind: 'news', title: 'Story' });
    expect(m.popupState().toasts.map((t) => t.id)).toEqual(['z']);
    expect(m.popupState().history.map((t) => t.id)).toEqual(['z', 'y', 'x']);
    const again = await fresh();                                           // settings survive a reload
    expect(again.popupState().kinds.eco).toBe(false);
    expect(again.popupState().enabled).toBe(true);
  });

  it('remembers what was already notified this session', async () => {
    const m = await fresh();
    expect(m.seenBefore('k1')).toBe(false);
    expect(m.seenBefore('k1')).toBe(true);
    const again = await fresh();
    expect(again.seenBefore('k1')).toBe(true);
  });
});
