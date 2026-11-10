import type {StreamStatus} from '@/store/mlStreamStore';

/** Which transport the observability panels are actually reading from.
 *
 * The store has carried status, reconnects and coalesced-frame gaps since the client was added, and
 * nothing rendered any of it — so a panel quietly polling on a dropped socket looked identical to one
 * being pushed to, and a refused token looked like a slow page. The badge exists to make that
 * distinction legible rather than to decorate the toolbar: it claims "live push" only while the
 * socket is open, because that is the only condition under which the panels switch their polls off.
 */
const LABEL: Record<StreamStatus, string> = {
  open: 'Live push',
  connecting: 'Stream connecting',
  closed: 'Stream dropped · polling',
  unauthorized: 'Stream refused · polling',
  error: 'Stream error · polling',
  idle: 'Polling',
};

export function StreamBadge({ status, error, reconnects, gaps }: {
  status: StreamStatus; error: string | null; reconnects: number; gaps: Record<string, number>;
}) {
  const dropped = Object.values(gaps).reduce((a, b) => a + b, 0);
  const detail = [
    status === 'open'
      ? 'The measured network, provider supervision, evidence map and learning panels are being pushed to; their own polls are off.'
      : 'The observability panels are polling on their own timers instead.',
    reconnects > 0 ? `Reconnected ${reconnects}× since this page was opened.` : '',
    dropped > 0 ? `${dropped} frames were coalesced away because they arrived faster than they were read.` : '',
    error ? `Last reported: ${error}` : '',
  ].filter(Boolean).join(' ');
  return <span className="ml-pill" data-tone={status === 'open' ? 'ok' : status === 'connecting' || status === 'idle' ? 'shadow' : 'warn'}
    title={detail} role="status">{LABEL[status]}</span>;
}
