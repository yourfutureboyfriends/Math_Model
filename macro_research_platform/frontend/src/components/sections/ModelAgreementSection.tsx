// Phase 8 — Model Agreement Section (Redesigned)
// Model consensus with terminal aesthetic

import { CheckCircle, AlertTriangle, XCircle, Activity } from 'lucide-react';
import type { ModelAgreementData } from '@/types';

interface ModelAgreementSectionProps {
  data?: ModelAgreementData;
}

export function ModelAgreementSection({ data }: ModelAgreementSectionProps) {
  if (!data?.items?.length) return null;

  const getImpactIcon = (color: string) => {
    switch (color) {
      case 'success':
        return <CheckCircle className="w-3 h-3 text-green" />;
      case 'warning':
        return <AlertTriangle className="w-3 h-3 text-amber" />;
      case 'danger':
        return <XCircle className="w-3 h-3 text-red" />;
      default:
        return null;
    }
  };

  const getImpactColor = (color: string) => {
    switch (color) {
      case 'success':
        return 'text-green';
      case 'warning':
        return 'text-amber';
      case 'danger':
        return 'text-red';
      case 'info':
        return 'text-blue';
      default:
        return 'text-text-tertiary';
    }
  };

  return (
    <div id="model-agreement" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">30</span>
          <h2 className="section-title">Model Agreement</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Summary */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <Activity className="w-3 h-3 text-amber" />
            <span>Consensus across multiple models</span>
          </div>
        </div>

        {/* Agreement Table */}
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
              {data.items.map((item, idx) => (
                <tr key={`${item.model}-${item.indicator}-${idx}`} className="border-b border-border-subtle last:border-0">
                  <td className="py-2 px-3 text-xs font-medium text-text-primary">{item.model}</td>
                  <td className="py-2 px-3 text-xs text-text-secondary">{item.indicator}</td>
                  <td className="py-2 px-3 text-center">
                    <div className="flex items-center justify-center gap-2">
                      {getImpactIcon(item.color)}
                      <span className={`text-xs font-medium ${getImpactColor(item.color)}`}>
                        {item.impact}
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
