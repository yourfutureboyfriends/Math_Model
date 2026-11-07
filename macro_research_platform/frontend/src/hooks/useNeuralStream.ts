/**
 * useNeuralStream — subscribe to the ML observability push stream.
 *
 * Replaces polling api/v1/ml/deep/live/refresh, online/status, research/graph and
 * autonomous/status on timers. The backend samples only while a client is subscribed, so mounting
 * this hook is what makes the work happen and unmounting it is what stops it.
 *
 * Two rules the 60fps requirement imposes:
 *
 *   1. The hook returns coarse connection state only. Frames land in the store; a component that
 *      re-renders per frame would defeat the point of pushing instead of polling.
 *   2. Animation loops read through `readFrame`/`readPayload`, which never subscribe.
 *
 * Authentication: the token goes in the subscribe payload, not the handshake, matching the backend.
 * It is read at subscribe time so a token refreshed while the socket was down is used on reconnect,
 * and the subscribe is re-issued on every `connect` — Socket.IO reconnects the transport but does
 * not replay application-level subscriptions.
 */
import { useEffect } from 'react';
import { type Socket, io } from 'socket.io-client';

import { getApiBaseUrl } from '@/lib/network';
import {
  type StreamFrame,
  type StreamStatus,
  type StreamTopic,
  useMlStreamStore,
} from '@/store/mlStreamStore';

const SUBSCRIBE_EVENT = 'subscribe_ml_stream';
const UNSUBSCRIBE_EVENT = 'unsubscribe_ml_stream';
const ACK_EVENT = 'ml_stream_state';
const ERROR_EVENT = 'ml_stream_error';

/** Socket.IO needs an absolute origin; the production API base is the relative "/api". */
export function streamOrigin(): string {
  const base = getApiBaseUrl();
  if (/^https?:\/\//i.test(base)) return base.replace(/\/$/, '');
  if (typeof window !== 'undefined') return window.location.origin;
  return 'http://localhost:8000';
}

interface Options {
  /** Bearer token from useAuth(). Without it the hook stays closed rather than failing loudly. */
  token: string | null;
  /** Set false to tear the connection down without unmounting, e.g. when the tab is hidden. */
  enabled?: boolean;
  topics?: StreamTopic[];
}

interface Result {
  status: StreamStatus;
  error: string | null;
  reconnects: number;
  /** Dropped frames per channel from last-value coalescing. Non-zero is normal under load. */
  gaps: Record<string, number>;
}

export function useNeuralStream({
  token,
  enabled = true,
  topics = ['system1_inference', 'system2_reasoning'],
}: Options): Result {
  const status = useMlStreamStore((s) => s.status);
  const error = useMlStreamStore((s) => s.error);
  const reconnects = useMlStreamStore((s) => s.reconnects);
  const gaps = useMlStreamStore((s) => s.gaps);

  // A stable key so changing the array literal's identity does not reconnect on every render.
  const topicKey = topics.join(',');

  useEffect(() => {
    const store = useMlStreamStore.getState();
    if (!enabled || !token) {
      store.setStatus('idle');
      return;
    }

    const wanted = topicKey.split(',') as StreamTopic[];
    let socket: Socket | null = null;
    let disposed = false;
    let firstConnect = true;

    store.setStatus('connecting');

    const subscribeAll = () => {
      for (const topic of wanted) {
        socket?.emit(SUBSCRIBE_EVENT, { topic, auth: { token } });
      }
    };

    try {
      socket = io(streamOrigin(), {
        transports: ['websocket', 'polling'],
        withCredentials: false,
        // The backend samples only while subscribed, so reconnect promptly but not hotly.
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 15000,
        randomizationFactor: 0.5,
        timeout: 10000,
      });
    } catch (err) {
      store.setStatus('error', err instanceof Error ? err.message : String(err));
      return;
    }

    const onConnect = () => {
      if (disposed) return;
      if (firstConnect) firstConnect = false;
      else useMlStreamStore.getState().noteReconnect();
      useMlStreamStore.getState().setStatus('open');
      subscribeAll();
    };

    const onFrame = (_event: string, frame: StreamFrame) => {
      if (disposed || !frame || typeof frame.channel !== 'string') return;
      // A schema the client does not understand is worse than a missing frame: refuse it rather
      // than rendering fields that moved meaning.
      if (frame.v !== 1) {
        useMlStreamStore.getState().setStatus('error', `Unsupported stream schema v${frame.v}`);
        return;
      }
      useMlStreamStore.getState().accept(frame);
    };

    const onError = (payload: { error?: string; detail?: string }) => {
      if (disposed) return;
      const detail = payload?.detail ?? 'stream error';
      if (payload?.error === 'unauthorized') {
        useMlStreamStore.getState().setStatus('unauthorized', detail);
        socket?.disconnect();               // retrying with the same token cannot succeed
      } else {
        useMlStreamStore.getState().setStatus('error', detail);
      }
    };

    // The ack replays the last frame per channel, so a freshly mounted panel is populated at once
    // instead of waiting up to one sample interval.
    const onAck = (state: { topic?: string; state?: Record<string, StreamFrame> }) => {
      if (disposed || !state?.state) return;
      const accept = useMlStreamStore.getState().accept;
      for (const frame of Object.values(state.state)) {
        if (!frame || typeof frame.channel !== 'string') continue;
        // The replayed snapshot gets the same schema gate as a live frame, or a version bump would
        // be rejected on the stream and silently accepted here.
        if (frame.v !== 1) {
          useMlStreamStore.getState().setStatus('error', `Unsupported stream schema v${frame.v}`);
          return;
        }
        accept(frame);
      }
    };

    const onDisconnect = (reason: string) => {
      if (disposed) return;
      // 'io client disconnect' means we tore it down on purpose; anything else is a dropped link
      // that Socket.IO will retry, so report closed rather than error.
      useMlStreamStore.getState().setStatus(reason === 'io client disconnect' ? 'idle' : 'closed');
    };

    // One listener for every frame event. They are named `${topic}:${channel}` and the channel set
    // is defined server-side, so route by prefix rather than enumerating channels here.
    const onAny = (event: string, frame: StreamFrame) => {
      if (wanted.some((topic) => event.startsWith(`${topic}:`))) onFrame(event, frame);
    };

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    socket.on(ERROR_EVENT, onError);
    socket.on(ACK_EVENT, onAck);
    socket.onAny(onAny);

    return () => {
      disposed = true;
      if (socket) {
        for (const topic of wanted) socket.emit(UNSUBSCRIBE_EVENT, { topic });
        socket.offAny(onAny);
        socket.off('connect', onConnect);
        socket.off('disconnect', onDisconnect);
        socket.off(ERROR_EVENT, onError);
        socket.off(ACK_EVENT, onAck);
        socket.disconnect();
      }
      useMlStreamStore.getState().setStatus('idle');
    };
  }, [enabled, token, topicKey]);

  return { status, error, reconnects, gaps };
}
