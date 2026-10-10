/**
 * DataIntegrityIndicator — Phase 1B header widget.
 *
 * Shows the share of model inputs that are current against their RELEASE CALENDAR
 * ("INTEGRITY 94%") — i.e. the latest period that should be published by now is present —
 * from /api/v1/freshness. Inputs that could not be checked are reported, not counted fresh. Green
 * ≥ 90%, amber 70–89%, red < 70%. Hover for the fresh / stale / critical breakdown and the
 * specific metrics that are out of tolerance — so a PM sees at a glance whether the board
 * as a whole can be trusted right now.
 */
import { useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { useFreshness } from '@/hooks/useFreshness';

export function DataIntegrityIndicator() {
  const data = useFreshness();
  const [open, setOpen] = useState(false);

  const series = data?.series ?? [];
  const known = series.filter((s) => s.status !== 'UNKNOWN');
  const fresh = known.filter((s) => s.status === 'FRESH');
  const stale = known.filter((s) => s.status === 'STALE');
  const critical = known.filter((s) => s.status === 'CRITICAL');
  const pct = known.length ? Math.round((fresh.length / known.length) * 100) : null;
  const unknown = series.length - known.length;
  const awaiting = known.filter((s) => s.state === 'DUE');
  const upcoming = known.filter((s) => s.next_expected_release && s.frequency !== 'D')
    .sort((a, b) => (a.next_expected_release! < b.next_expected_release! ? -1 : 1)).slice(0, 4);

  const tone = pct == null ? 'text-text-tertiary' : pct >= 90 ? 'text-green' : pct >= 70 ? 'text-amber' : 'text-red';
  const dot = pct == null ? 'bg-text-tertiary' : pct >= 90 ? 'bg-green' : pct >= 70 ? 'bg-amber' : 'bg-red';

  return (
    <span className="relative" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <span className={`inline-flex items-center gap-1 font-mono border border-border px-2 py-0.5 cursor-default ${tone}`}
        style={{ fontSize: 10, letterSpacing: '0.06em' }}>
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${dot}`} />
        <ShieldCheck className="w-3 h-3" />
        INTEGRITY {pct == null ? '—' : `${pct}%`}
      </span>

      {open && known.length > 0 && (
        <div className="absolute right-0 top-6 z-50 w-72 p-2.5 bg-surface-2 border border-border-strong text-2xs font-mono">
          <div className="flex items-center justify-between mb-1.5 pb-1.5 border-b border-border-subtle">
            <span className="uppercase tracking-wider text-text-tertiary">Data Integrity</span>
            <span className={tone}>{fresh.length}/{known.length} current</span>
          </div>
          <div className="flex gap-3 mb-1.5">
            <span className="text-green">● {fresh.length} fresh</span>
            {stale.length > 0 && <span className="text-amber">● {stale.length} stale</span>}
            {critical.length > 0 && <span className="text-red">● {critical.length} critical</span>}
            {unknown > 0 && <span className="text-text-tertiary">● {unknown} unchecked</span>}
          </div>
          <div className="text-text-tertiary mb-1.5">Graded against each series' release calendar.</div>
          {[...critical, ...stale].slice(0, 6).map((s) => (
            <div key={s.metric} className="flex justify-between">
              <span className="text-text-secondary truncate">{s.name}</span>
              <span className={s.status === 'CRITICAL' ? 'text-red' : 'text-amber'}>
                {s.status === 'CRITICAL' ? 'MISSING' : 'LATE'}{s.periods_behind ? ` ${s.periods_behind}p` : ''}
              </span>
            </div>
          ))}
          {stale.length + critical.length === 0 && <div className="text-green">All inputs current.</div>}
          {awaiting.length > 0 && (
            <div className="mt-1 text-text-tertiary">Release window open: {awaiting.map((s) => s.name).join(', ')}</div>
          )}
          {upcoming.length > 0 && (
            <div className="mt-1.5 pt-1.5 border-t border-border-subtle">
              <div className="uppercase tracking-wider text-text-tertiary mb-0.5">Next releases</div>
              {upcoming.map((s) => (
                <div key={s.metric} className="flex justify-between">
                  <span className="text-text-secondary truncate">{s.name}</span>
                  <span className="text-text-tertiary">~{s.next_expected_release}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </span>
  );
}
