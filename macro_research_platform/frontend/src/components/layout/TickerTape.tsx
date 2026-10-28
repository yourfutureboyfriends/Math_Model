// Live ticker tape: a continuously scrolling strip of ~50 instruments, ordered the way the trading day travels round
// the world (Asia-Pacific → EMEA → Americas, then rates, FX, commodities and crypto). Each quote shows price, day
// change with an up / down arrow and a 60-day sparkline, and flashes green or red when it ticks. Hover pauses the
// crawl; a click opens the chart.
//
// Data: the shared market feed (lib/marketPulse — Yahoo Finance, delayed, polled once a minute).
import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { openChart } from '@/components/ui/ChartModal';
import { fmtPulseChange, fmtPulsePrice, SHORT, TAPE_SECTIONS, useMarketPulse, type PulseRow } from '@/lib/marketPulse';
import { cn } from '@/lib/utils';

/** A tiny 60-day sparkline coloured by the period's direction. */
function MiniSpark({ data }: { data: number[] }) {
  if (data.length < 2) return null;
  const w = 36, h = 12;
  const lo = Math.min(...data), hi = Math.max(...data), span = hi - lo || 1;
  const pts = data.map((v, i) => `${((i / (data.length - 1)) * w).toFixed(1)},${(h - ((v - lo) / span) * h).toFixed(1)}`).join(' ');
  const up = data[data.length - 1] >= data[0];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="shrink-0" aria-hidden>
      <polyline points={pts} fill="none" strokeWidth={1} strokeLinejoin="round"
        stroke={up ? 'rgb(var(--c-green))' : 'rgb(var(--c-red))'} opacity={0.85} />
    </svg>
  );
}

/** Flash class for a value that changed since the last render ('flash-up' / 'flash-down' for 1.2 s). */
export function useTickFlash(value: number | null | undefined): string {
  const prev = useRef(value);
  const [flash, setFlash] = useState('');
  useEffect(() => {
    if (value != null && prev.current != null && value !== prev.current) {
      setFlash(value > prev.current ? 'flash-up' : 'flash-down');
      prev.current = value;
      const t = setTimeout(() => setFlash(''), 1200);
      return () => clearTimeout(t);
    }
    prev.current = value;
  }, [value]);
  return flash;
}

const Quote = memo(function Quote({ r }: { r: PulseRow }) {
  const flash = useTickFlash(r.price);
  const c = fmtPulseChange(r);
  return (
    <button type="button" className={cn('tape-quote', flash)} onClick={() => openChart(r.symbol, r.name)}
      data-symbol={r.symbol} aria-label={`${r.name} (${r.symbol}) — open the chart`}>
      <span className="tape-sym">{SHORT[r.symbol] ?? r.symbol}</span>
      <span className="tape-px">{r.live && <span className="tape-live" aria-label="streaming" />}{fmtPulsePrice(r)}</span>
      {c.text && (
        <span className={cn('tape-chg', c.dir > 0 ? 'text-green' : c.dir < 0 ? 'text-red' : 'text-text-tertiary')}>
          {c.dir > 0 ? '▲' : c.dir < 0 ? '▼' : '■'} {c.text}
        </span>
      )}
      {r.spark && <MiniSpark data={r.spark} />}
    </button>
  );
});

export function TickerTape() {
  const { rows, asOf, status } = useMarketPulse();

  const items = useMemo(() => TAPE_SECTIONS.flatMap((s) => {
    const qs = s.symbols.map((sym) => rows[sym]).filter((r): r is PulseRow => !!r && r.price != null);
    return qs.length ? [{ tag: s.tag, rows: qs }] : [];
  }), [rows]);
  const count = items.reduce((n, s) => n + s.rows.length + 1, 0);
  const duration = Math.max(60, count * 4.5);        // same pace (~40 px/s) however many quotes

  const track = (copy: number) => items.map((s) => (
    <span key={`${copy}-${s.tag}`} className="tape-section">
      <span className="tape-tag">{s.tag}</span>
      {s.rows.map((r) => <Quote key={r.symbol} r={r} />)}
    </span>
  ));

  return (
    <div className="tape" aria-label="World markets ticker tape">
      <div className="tape-label" title={`Yahoo Finance, delayed (crypto streams live from Coinbase)${asOf ? ` — refreshed ${new Date(asOf).toLocaleTimeString()}` : ''}. Hover to pause, click a quote for its chart.`}>
        <span className={cn('tape-dot', status === 'error' ? 'bg-red' : status === 'ok' ? 'bg-green' : 'bg-amber')} />
        {status === 'error' && !count ? 'OFFLINE' : 'WORLD'}
      </div>
      <div className="tape-viewport">
        {count === 0 ? (
          <span className="tape-empty">{status === 'error' ? 'Market data unavailable — retrying every minute' : 'Loading world markets…'}</span>
        ) : (
          // two identical copies: translating by −50 % loops seamlessly
          <div className="tape-track" style={{ animationDuration: `${duration}s` }}>{track(0)}{track(1)}</div>
        )}
      </div>
    </div>
  );
}
