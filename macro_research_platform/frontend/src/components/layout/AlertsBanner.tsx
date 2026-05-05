// ADDED: Phase 5 Task 1 — Alerts Banner Component
// Displays active alerts at the top of the dashboard with severity-based styling

import { useState } from 'react';
import { AlertItem, AlertsData } from '@/types';
import { X, AlertCircle, AlertTriangle, Info } from 'lucide-react';

interface AlertsBannerProps {
  alerts?: AlertsData;
  onAcknowledge?: (alertId: string) => void;
}

export function AlertsBanner({ alerts, onAcknowledge }: AlertsBannerProps) {
  const [dismissedAlerts, setDismissedAlerts] = useState<Set<string>>(new Set());

  if (!alerts || !alerts.active || alerts.active.length === 0) {
    return null;
  }

  // Filter out dismissed alerts
  const visibleAlerts = alerts.active.filter(
    alert => !dismissedAlerts.has(alert.id) && !alert.acknowledged
  );

  if (visibleAlerts.length === 0) {
    return null;
  }

  const handleDismiss = (alertId: string) => {
    setDismissedAlerts(prev => new Set(prev).add(alertId));
    if (onAcknowledge) {
      onAcknowledge(alertId);
    }
  };

  // Sort by severity: critical > warning > info
  const severityOrder = { critical: 0, warning: 1, info: 2 };
  const sortedAlerts = [...visibleAlerts].sort(
    (a, b) => severityOrder[a.severity] - severityOrder[b.severity]
  );

  // Get banner background color based on highest severity
  const hasCritical = sortedAlerts.some(a => a.severity === 'critical');
  const hasWarning = sortedAlerts.some(a => a.severity === 'warning');

  const bannerClass = hasCritical
    ? 'bg-red-900/90 border-red-700'
    : hasWarning
    ? 'bg-amber-900/90 border-amber-700'
    : 'bg-slate-800/90 border-slate-700';

  return (
    <div className={`w-full ${bannerClass} border-b`}>
      <div className="max-w-[1920px] mx-auto">
        {sortedAlerts.map((alert) => (
          <AlertRow
            key={alert.id}
            alert={alert}
            onDismiss={() => handleDismiss(alert.id)}
          />
        ))}
      </div>
    </div>
  );
}

interface AlertRowProps {
  alert: AlertItem;
  onDismiss: () => void;
}

function AlertRow({ alert, onDismiss }: AlertRowProps) {
  const severityConfig = {
    critical: {
      icon: AlertCircle,
      iconClass: 'text-red-400',
      bgClass: 'bg-red-950/50',
      pulse: true,
    },
    warning: {
      icon: AlertTriangle,
      iconClass: 'text-amber-400',
      bgClass: 'bg-amber-950/50',
      pulse: false,
    },
    info: {
      icon: Info,
      iconClass: 'text-slate-400',
      bgClass: 'bg-slate-900/50',
      pulse: false,
    },
  };

  const config = severityConfig[alert.severity];
  const Icon = config.icon;

  return (
    <div
      className={`flex items-start gap-3 px-6 py-3 ${config.bgClass} border-b border-white/5 last:border-b-0`}
    >
      {/* Severity Icon */}
      <div className={`flex-shrink-0 mt-0.5 ${config.pulse ? 'animate-pulse' : ''}`}>
        <Icon className={`w-5 h-5 ${config.iconClass}`} />
      </div>

      {/* Alert Content */}
      <div className="flex-1 min-w-0">
        <div className="flex flex-col sm:flex-row sm:items-center sm:gap-4">
          {/* Message */}
          <p className="text-sm text-white font-medium truncate">
            {alert.message}
          </p>

          {/* Action Text */}
          <p className="text-xs text-white/70 mt-1 sm:mt-0 sm:ml-auto flex-shrink-0">
            {alert.action}
          </p>
        </div>

        {/* Value vs Threshold */}
        <div className="flex items-center gap-2 mt-1 text-xs text-white/50">
          <span>Current: {alert.currentValue}</span>
          <span className="text-white/30">|</span>
          <span>Threshold: {alert.threshold}</span>
          {alert.triggeredAt && (
            <>
              <span className="text-white/30">|</span>
              <span>Since: {new Date(alert.triggeredAt).toLocaleDateString()}</span>
            </>
          )}
        </div>
      </div>

      {/* Dismiss Button */}
      <button
        onClick={onDismiss}
        className="flex-shrink-0 p-1 rounded hover:bg-white/10 transition-colors"
        aria-label="Dismiss alert"
      >
        <X className="w-4 h-4 text-white/70 hover:text-white" />
      </button>
    </div>
  );
}
