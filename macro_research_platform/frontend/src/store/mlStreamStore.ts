/**
 * ML stream store — latest frame per channel, plus connection health.
 *
 * The point of keeping this out of component state is frame rate. System 1 samples every two
 * seconds and a WebGL or canvas consumer wants the newest value on every animation frame, not a
 * React render per frame. So:
 *
 *   - `frames` is replaced wholesale per channel; a component that needs to re-render subscribes
 *     with a narrow selector (status, one channel's `seq`, a derived flag) and not to `frames`.
 *   - `readFrame` is a non-reactive getter for render loops. Call it inside useFrame/rAF; it never
 *     triggers a re-render, which is what keeps a 3D scene at 60fps.
 *
 * Nothing here invents a value. A frame carries `ok`; when a producer failed, `payload` is null and
 * `error` says why, so a panel can show the last good frame and a fault instead of a plausible zero.
 */
import { create } from 'zustand';

export type StreamTopic = 'system1_inference' | 'system2_reasoning';

export interface StreamFrame {
  v: number;
  topic: StreamTopic;
  channel: string;
  seq: number;
  ok: boolean;
  payload: unknown;
  error: string | null;
  computed_ms: number | null;
  sent_at: string;
}

export type StreamStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'unauthorized' | 'error';

interface MlStreamState {
  status: StreamStatus;
  /** Frames keyed by channel, not by topic: channel names are unique across both topics. */
  frames: Record<string, StreamFrame>;
  /** Reconnects since mount, so a flapping link is visible rather than silently self-healing. */
  reconnects: number;
  /** Frames dropped by last-value coalescing, per channel. A gap is expected under load. */
  gaps: Record<string, number>;
  error: string | null;
  setStatus: (status: StreamStatus, error?: string | null) => void;
  accept: (frame: StreamFrame) => void;
  noteReconnect: () => void;
  reset: () => void;
}

const INITIAL = {
  status: 'idle' as StreamStatus,
  frames: {} as Record<string, StreamFrame>,
  reconnects: 0,
  gaps: {} as Record<string, number>,
  error: null as string | null,
};

export const useMlStreamStore = create<MlStreamState>()((set, get) => ({
  ...INITIAL,

  setStatus: (status, error = null) => set({ status, error }),

  accept: (frame) => {
    const previous = get().frames[frame.channel];
    // A jump in seq means the broadcaster coalesced older frames away. That is the designed
    // behaviour, not a loss to hide, so it is counted and surfaced.
    const skipped = previous && frame.seq > previous.seq + 1 ? frame.seq - previous.seq - 1 : 0;
    set((state) => ({
      frames: { ...state.frames, [frame.channel]: frame },
      gaps: skipped ? { ...state.gaps, [frame.channel]: (state.gaps[frame.channel] ?? 0) + skipped } : state.gaps,
    }));
  },

  noteReconnect: () => set((state) => ({ reconnects: state.reconnects + 1 })),

  reset: () => set({ ...INITIAL }),
}));

/** Non-reactive read for animation loops. Never subscribes, so it never causes a render. */
export function readFrame(channel: string): StreamFrame | undefined {
  return useMlStreamStore.getState().frames[channel];
}

/** The newest payload for a channel, or undefined if it has not arrived or its producer failed. */
export function readPayload<T = unknown>(channel: string): T | undefined {
  const frame = readFrame(channel);
  return frame && frame.ok ? (frame.payload as T) : undefined;
}
