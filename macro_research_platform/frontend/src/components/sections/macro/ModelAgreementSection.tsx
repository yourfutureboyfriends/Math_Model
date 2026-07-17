// Phase 8 — Model Agreement Section (Redesigned)
// Model consensus with terminal aesthetic

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
            <span className="section-tag">◆</span>
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
          <span className="section-tag">◆</span>
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
