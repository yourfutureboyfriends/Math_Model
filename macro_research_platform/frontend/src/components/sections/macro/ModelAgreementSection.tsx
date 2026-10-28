// Phase 8 — Model Agreement Section (Redesigned)
// Model consensus with terminal aesthetic

import { LineChart } from '@/components/ui/LineChart';
import { useApiData } from '@/hooks/useApiData';
import { CheckCircle, AlertTriangle, XCircle, Activity } from 'lucide-react';
import { ComputedTag } from '@/components/ui/ComputedTag';
import type { ModelAgreementData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface ModelAgreementSectionProps {
  data?: ModelAgreementData;
}

export function ModelAgreementSection({ data }: ModelAgreementSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  if (!data) data = (_fullDash as any)?.["modelAgreement"] as any;
  const d = data as any;

  // Explicit empty state instead of a blank panel when the dashboard hasn't provided this yet.
  if (!d || (d.agreementScore == null && !d.items?.length && !d.disagreements)) {
    return (
      <div id="model-agreement" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag" aria-hidden />
            <h2 className="section-title">Model Agreement</h2>
          </div>
        </div>
        <div className="p-4 text-2xs text-text-tertiary">Model consensus data unavailable.</div>
      </div>
    );
  }

  // Backend shape: { agreementScore (0-1), agreementLabel, disagreements: [{model, indicator, impact, color}] }.
  const score = typeof d.agreementScore === 'number' ? d.agreementScore : null;
  const label = d.agreementLabel || (score != null ? (score >= 0.7 ? 'High' : score >= 0.4 ? 'Moderate' : 'Low') : '—');
  // Support both the current `disagreements` field and the legacy `items` field.
  const rows: any[] = d.disagreements?.length ? d.disagreements : (d.items ?? []);
  const scoreTone = score == null ? 'text-text-primary' : score >= 0.7 ? 'text-green' : score >= 0.4 ? 'text-amber' : 'text-red';

  const impactIcon = (color: string) =>
    color === 'success' ? <CheckCircle className="w-3 h-3 text-green" />
      : color === 'warning' ? <AlertTriangle className="w-3 h-3 text-amber" />
      : color === 'danger' ? <XCircle className="w-3 h-3 text-red" /> : null;
  const impactColor = (color: string) =>
    color === 'success' ? 'text-green' : color === 'warning' ? 'text-amber'
      : color === 'danger' ? 'text-red' : color === 'info' ? 'text-blue' : 'text-text-tertiary';

  return (
    <div id="model-agreement" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag" aria-hidden />
          <h2 className="section-title">Model Agreement</h2>
        </div>
        <ComputedTag section="modelAgreement" />
      </div>

      <div className="space-y-3">
        {/* Headline consensus */}
        <div className="p-3 bg-surface-1 border border-border flex items-center gap-3">
          <Activity className="w-4 h-4 text-amber" />
          <div>
            <div className="text-2xs text-text-tertiary uppercase tracking-wider">Consensus across models</div>
            <div className="flex items-baseline gap-2">
              <span className={`text-2xl font-mono font-bold tabular-nums ${scoreTone}`}>
                {score != null ? score.toFixed(2) : '—'}
              </span>
              <span className={`text-xs font-mono uppercase ${scoreTone}`}>{label} agreement</span>
            </div>
          </div>
          <span className="ml-auto text-2xs text-text-tertiary">{rows.length} disagreement{rows.length === 1 ? '' : 's'}</span>
        </div>

        {(d.effectiveVotes != null || d.inputs?.length) && (
          <div className="border border-border bg-surface-1 p-2 text-2xs text-text-secondary space-y-1">
            {d.effectiveVotes != null && (
              <div>Agreement counts each data driver once ({d.effectiveVotes} drivers: {Object.entries(d.driverShares ?? {}).map(([k, v]) => `${k} ${Math.round((v as number) * 100)}% bullish`).join(' · ')}); raw vote share {d.rawAgreement != null ? Math.round(d.rawAgreement * 100) + '%' : '—'}.</div>
            )}
            {d.inputs?.length > 0 && (
              <table className="w-full mt-1">
                <thead><tr className="text-text-tertiary uppercase"><th className="text-left font-medium">Score input</th><th className="text-right font-medium">Weight</th><th className="text-left font-medium pl-3">Out-of-sample evidence</th></tr></thead>
                <tbody>
                  {d.inputs.map((c: any) => (
                    <tr key={c.name} className="border-t border-border-subtle">
                      <td className="py-1 text-text-primary">{c.name}</td>
                      <td className="py-1 text-right font-mono">{c.weight != null ? `${Math.round(c.weight * 100)}%` : '—'}</td>
                      <td className="py-1 pl-3"><span className={c.status === 'FAIL' ? 'text-red' : c.status === 'PASS' ? 'text-green' : 'text-amber'}>{c.status ?? '—'}</span> <span className="text-text-tertiary">{c.reason}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        <CompositeHistory />

        {/* Disagreements table, or an "all agree" note */}
        {rows.length > 0 ? (
          <div className="border border-border bg-surface-1 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border-subtle bg-surface-2">
                  <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Model</th>
                  <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Indicator</th>
                  <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Impact</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item, idx) => (
                  <tr key={`${item.model}-${item.indicator}-${idx}`} className="border-b border-border-subtle last:border-0">
                    <td className="py-2 px-3 text-xs font-medium text-text-primary">{item.model}</td>
                    <td className="py-2 px-3 text-xs text-text-secondary">{item.indicator}</td>
                    <td className="py-2 px-3 text-center">
                      <div className="flex items-center justify-center gap-2">
                        {impactIcon(item.color)}
                        <span className={`text-xs font-medium ${impactColor(item.color)}`}>{item.impact}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-3 bg-surface-1 border border-border text-xs text-green flex items-center gap-2">
            <CheckCircle className="w-3.5 h-3.5" /> All models agree — no material disagreements.
          </div>
        )}
      </div>
    </div>
  );
}


// Weekly composite-signal history (inputs re-evaluated with data as of each date, today's evidence weights).
function CompositeHistory() {
  const { data } = useApiData<any>('/api/v1/signals/composite-history?weeks=104');
  if (!data?.available || !data.points?.length) return null;
  const st = data.forward_return_by_state ?? {};
  const f = (v: number | null | undefined) => (v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(2)}%`);
  return (
    <div className="border border-border bg-surface-1 p-2">
      <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Composite signal — 2 years, weekly</div>
      <LineChart rows={data.points} x="date" height={200} fmt={(v) => v.toFixed(2)} refs={[{ value: 0.6, label: 'bullish' }, { value: 0.4, label: 'bearish' }]}
        lines={[{ key: 'composite', label: 'Composite', color: '#3987e5' }, { key: 'growth', label: 'Growth', color: '#199e70' },
          { key: 'liquidity', label: 'Liquidity', color: '#c98500' }]} />
      <div className="text-[10px] text-text-tertiary mt-1">
        S&amp;P 500 next month: composite &gt; 0.6 {f(st['composite > 0.6']?.avg_spx_1m)} ({st['composite > 0.6']?.weeks ?? 0} wks) ·
        &lt; 0.4 {f(st['composite < 0.4']?.avg_spx_1m)} ({st['composite < 0.4']?.weeks ?? 0} wks) · all {f(st.all?.avg_spx_1m)}. {data.method}
      </div>
    </div>
  );
}
