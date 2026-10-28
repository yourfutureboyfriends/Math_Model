// Phase 8 Alerts Panel
// Slide-out panel from right side

import { useEffect, useState } from 'react';
import { X, AlertTriangle, AlertCircle, Info } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Alert {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  timestamp: string;
  title: string;
  description: string;
  action?: string;
  acknowledged: boolean;
}

interface AlertsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  alerts?: Alert[];
  onAcknowledge?: (id: string) => void;
  onViewSection?: (section: string) => void;
}

// Live alerts from /api/alerts (rule-based on real market conditions). This panel used to
// show two hard-coded "mock" alerts (e.g. "GPR at 1.24σ", dated May 2026) on every open.
const SEVERITY: Record<string, Alert['severity']> = { High: 'critical', Critical: 'critical', Medium: 'warning', Low: 'info' };
const ACTION: Record<string, string> = { Rates: 'yield-curve', Recession: 'regime', Volatility: 'risk-indicators' };

function useLiveAlerts(enabled: boolean): Alert[] | null {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    fetch('/api/alerts')
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (cancelled || !j) return;
        setAlerts((j.alerts ?? []).filter((a: any) => a.active !== false && a.id !== 'alert-normal').map((a: any) => ({
          id: a.id, severity: SEVERITY[a.severity] ?? 'info', timestamp: a.timestamp,
          title: a.type ?? 'Alert', description: a.message, action: ACTION[a.type], acknowledged: false,
        })));
      })
      .catch(() => { if (!cancelled) setAlerts([]); });
    return () => { cancelled = true; };
  }, [enabled]);
  return alerts;
}

export function AlertsPanel({
  isOpen,
  onClose,
  alerts: alertsProp,
  onAcknowledge,
  onViewSection,
}: AlertsPanelProps) {
  const live = useLiveAlerts(isOpen && !alertsProp);
  const alerts: Alert[] = alertsProp ?? live ?? [];
  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'critical':
        return <AlertCircle className="w-3 h-3 text-red" />;
      case 'warning':
        return <AlertTriangle className="w-3 h-3 text-amber" />;
      default:
        return <Info className="w-3 h-3 text-blue" />;
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'border-l-red';
      case 'warning':
        return 'border-l-amber';
      default:
        return 'border-l-blue';
    }
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      month: 'short',
      day: 'numeric',
    });
  };

  const unacknowledged = alerts.filter((a) => !a.acknowledged);

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40"
          onClick={onClose}
        />
      )}

      {/* Panel */}
      <div
        className={cn(
          'fixed top-16 right-0 bottom-0 w-80 bg-surface-1 border-l border-border z-50',
          'transform transition-transform duration-200 ease-out',
          isOpen ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        {/* Header */}
        <div className="h-12 flex items-center justify-between px-4 border-b border-border">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-text-primary">Alerts</span>
            {unacknowledged.length > 0 && (
              <span className="px-1.5 py-0.5 text-2xs font-mono bg-amber-dim text-amber rounded-sm"
              >
                {unacknowledged.length}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 text-text-tertiary hover:text-text-primary transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Alerts list */}
        <div className="overflow-y-auto">
          {alerts.length === 0 ? (
            <div className="p-8 text-center text-text-tertiary text-sm">
              No active alerts
            </div>
          ) : (
            <div className="divide-y divide-border-subtle">
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  className={cn(
                    'p-4 border-l-2',
                    getSeverityColor(alert.severity),
                    !alert.acknowledged && 'bg-surface-2'
                  )}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      {getSeverityIcon(alert.severity)}
                      <span className={cn(
                        'text-2xs uppercase tracking-wider font-medium',
                        alert.severity === 'critical' && 'text-red',
                        alert.severity === 'warning' && 'text-amber',
                        alert.severity === 'info' && 'text-blue'
                      )}>
                        {alert.severity}
                      </span>
                    </div>
                    <span className="text-2xs text-text-tertiary font-mono">
                      {formatTime(alert.timestamp)}
                    </span>
                  </div>

                  <div className="mb-2">
                    <div className="text-sm font-medium text-text-primary mb-1">
                      {alert.title}
                    </div>
                    <div className="text-xs text-text-secondary">
                      {alert.description}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {alert.action && (
                      <button
                        onClick={() => onViewSection?.(alert.action!)}
                        className="px-2 py-1 text-2xs font-medium text-bloomberg border border-bloomberg/30 rounded-sm hover:bg-bloomberg-muted transition-colors"
                      >
                        VIEW SECTION
                      </button>
                    )}
                    {!alert.acknowledged && (
                      <button
                        onClick={() => onAcknowledge?.(alert.id)}
                        className="px-2 py-1 text-2xs font-medium text-text-secondary hover:text-text-primary transition-colors"
                      >
                        DISMISS
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
