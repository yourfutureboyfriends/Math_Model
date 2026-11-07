import { beforeEach, describe, expect, it } from 'vitest';

import {
  type StreamFrame,
  readFrame,
  readPayload,
  useMlStreamStore,
} from './mlStreamStore';

const frame = (channel: string, overrides: Partial<StreamFrame> = {}): StreamFrame => ({
  v: 1,
  topic: 'system1_inference',
  channel,
  seq: 1,
  ok: true,
  payload: { value: 1 },
  error: null,
  computed_ms: 12.5,
  sent_at: '2026-01-01T00:00:00.000+00:00',
  ...overrides,
});

describe('mlStreamStore', () => {
  beforeEach(() => {
    useMlStreamStore.getState().reset();
  });

  it('starts idle with no frames, no gaps and no error', () => {
    const s = useMlStreamStore.getState();
    expect(s.status).toBe('idle');
    expect(s.frames).toEqual({});
    expect(s.gaps).toEqual({});
    expect(s.reconnects).toBe(0);
    expect(s.error).toBeNull();
  });

  it('keeps the latest frame per channel', () => {
    const { accept } = useMlStreamStore.getState();
    accept(frame('deep_live', { seq: 1, payload: { value: 'old' } }));
    accept(frame('deep_live', { seq: 2, payload: { value: 'new' } }));
    accept(frame('autonomous_status', { seq: 9 }));

    const s = useMlStreamStore.getState();
    expect(s.frames.deep_live.payload).toEqual({ value: 'new' });
    expect(Object.keys(s.frames)).toHaveLength(2);
  });

  it('counts coalesced frames as a gap on that channel', () => {
    const { accept } = useMlStreamStore.getState();
    accept(frame('deep_live', { seq: 1 }));
    accept(frame('deep_live', { seq: 4 }));
    // 2 and 3 were dropped by last-value coalescing.
    expect(useMlStreamStore.getState().gaps).toEqual({ deep_live: 2 });
  });

  it('records no gap entry at all when frames arrive contiguously', () => {
    const { accept } = useMlStreamStore.getState();
    accept(frame('deep_live', { seq: 1 }));
    accept(frame('deep_live', { seq: 2 }));
    accept(frame('deep_live', { seq: 3 }));
    expect(useMlStreamStore.getState().gaps).toEqual({});
  });

  it('never counts a gap on the first frame whatever its sequence number', () => {
    useMlStreamStore.getState().accept(frame('deep_live', { seq: 42 }));
    expect(useMlStreamStore.getState().gaps).toEqual({});
  });

  it('tracks gaps per channel independently', () => {
    const { accept } = useMlStreamStore.getState();
    accept(frame('deep_live', { seq: 1 }));
    accept(frame('online_status', { seq: 1 }));
    accept(frame('deep_live', { seq: 5 })); // 3 skipped here
    accept(frame('online_status', { seq: 2 })); // none there
    expect(useMlStreamStore.getState().gaps).toEqual({ deep_live: 3 });
  });

  it('setStatus carries an error and clears it on the next transition', () => {
    const { setStatus } = useMlStreamStore.getState();
    setStatus('error', 'boom');
    expect(useMlStreamStore.getState().error).toBe('boom');
    setStatus('open');
    const s = useMlStreamStore.getState();
    expect(s.status).toBe('open');
    expect(s.error).toBeNull();
  });

  it('counts reconnects and clears everything on reset', () => {
    const st = useMlStreamStore.getState();
    st.accept(frame('deep_live', { seq: 7 }));
    st.noteReconnect();
    st.noteReconnect();
    expect(useMlStreamStore.getState().reconnects).toBe(2);

    st.reset();
    const s = useMlStreamStore.getState();
    expect(s.frames).toEqual({});
    expect(s.gaps).toEqual({});
    expect(s.reconnects).toBe(0);
    expect(s.status).toBe('idle');
  });
});

describe('non-reactive reads', () => {
  beforeEach(() => {
    useMlStreamStore.getState().reset();
  });

  it('returns undefined for a channel that has not arrived', () => {
    expect(readFrame('deep_live')).toBeUndefined();
    expect(readPayload('deep_live')).toBeUndefined();
  });

  it('reads the newest frame without subscribing', () => {
    useMlStreamStore.getState().accept(frame('deep_live', { seq: 3, payload: { v: 'x' } }));
    expect(readFrame('deep_live')?.seq).toBe(3);
    expect(readPayload<{ v: string }>('deep_live')).toEqual({ v: 'x' });
  });

  it('withholds the payload of a failed sample instead of serving a stale one', () => {
    // The invariant that keeps a panel from rendering a plausible-looking zero: a producer that
    // threw reports ok:false with a null payload, and readPayload refuses to hand it over.
    useMlStreamStore.getState().accept(
      frame('deep_live', { seq: 1, ok: false, payload: null, error: 'collector unavailable' }),
    );
    expect(readPayload('deep_live')).toBeUndefined();
    // The frame itself is still readable, so a panel can show the fault and its reason.
    expect(readFrame('deep_live')?.error).toBe('collector unavailable');
  });
});
