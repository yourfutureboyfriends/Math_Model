// Phase 8 Alerts Panel
// Slide-out panel from right side

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

const mockAlerts: Alert[] = [
  {
    id: '1',
    severity: 'warning',
    timestamp: '2026-05-01T14:30:00Z',
    title: 'Geopolitical Risk Elevated',
    description: 'GPR at 1.24σ — widen position sizing',
    action: 'risk-indicators',
    acknowledged: false,
  },
  {
    id: '2',
    severity: 'info',
    timestamp: '2026-05-01T12:15:00Z',
    title: 'Model Weight Adapted',
    description: 'Momentum model weight reduced due to anomaly detection',
    acknowledged: false,
  },
];

export function AlertsPanel({
  isOpen,
  onClose,
  alerts = mockAlerts,
  onAcknowledge,
  onViewSection,
}: AlertsPanelProps) {
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
