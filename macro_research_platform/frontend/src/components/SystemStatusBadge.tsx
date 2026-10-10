/**
 * SystemStatusBadge — Phase 5: Real-time validation/health visibility
 *
 * Shows system health, validation status, and logging state.
 * Fetches from /api/health for real runtime data.
 */
import React, { useState } from 'react';
import { useApiData } from '@/hooks/useApiData';
import { Badge } from '@/components/ui/Badge';

interface HealthStatus {
  status: string;
  mode: string;
  models: {
    recession: boolean;
    lei: boolean;
    credit_impulse: boolean;
    risk_parity: boolean;
    fin_conditions: boolean;
    classifier: boolean;
  };
  data_rows: number;
  analyticalIntegrity: string;
  integrityErrors: string[];
}

interface SystemStatusBadgeProps {
  /** Show expanded details on hover/click */
  showDetails?: boolean;
  /** Compact mode - just the badge */
  compact?: boolean;
}

export function SystemStatusBadge({
  showDetails = true,
  compact = false,
}: SystemStatusBadgeProps): React.ReactElement {
  const [showTooltip, setShowTooltip] = useState(false);
  const { data, loading } = useApiData<HealthStatus>('/api/health');

  const getHealthStatus = (): { label: string; variant: 'success' | 'warning' | 'danger' | 'neutral' } => {
    if (loading || !data) return { label: 'LOADING', variant: 'neutral' };

    const status = data.status?.toLowerCase() || 'unknown';
    if (status === 'ok' || status === 'healthy') return { label: 'HEALTHY', variant: 'success' };
    if (status === 'degraded') return { label: 'DEGRADED', variant: 'warning' };
    return { label: 'ERROR', variant: 'danger' };
  };

  const getModelsStatus = (): { allActive: boolean; activeCount: number; total: number } => {
    if (!data?.models) return { allActive: false, activeCount: 0, total: 6 };
    const models = Object.values(data.models);
    const activeCount = models.filter(Boolean).length;
    return {
      allActive: activeCount === models.length,
      activeCount,
      total: models.length,
    };
  };

  const health = getHealthStatus();
  const models = getModelsStatus();

  if (compact) {
    return <Badge variant={health.variant}>{health.label}</Badge>;
  }

  return (
    <div
      className="relative inline-flex items-center gap-2"
      onMouseEnter={() => showDetails && setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      {/* Main Health Badge */}
      <Badge variant={health.variant}>{health.label}</Badge>

      {/* Models Status */}
      <Badge variant={models.allActive ? 'success' : 'warning'}>
        M:{models.activeCount}/{models.total}
      </Badge>

      {/* Mode Badge */}
      <Badge variant={data?.mode === 'live' ? 'success' : 'neutral'}>
        {data?.mode?.toUpperCase() || 'N/A'}
      </Badge>

      {/* Tooltip Details */}
      {showTooltip && data && (
        <div className="absolute top-full right-0 mt-2 z-50 min-w-[280px] p-3 bg-surface-1 border border-border-subtle shadow-lg rounded text-xs">
          <div className="space-y-2">
            <div className="font-medium text-text-primary border-b border-border-subtle pb-1">
              System Health
            </div>

            {/* Health Section */}
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              <span className="text-text-secondary">Status:</span>
              <span className={data.status === 'ok' ? 'text-green' : 'text-amber'}>
                {data.status?.toUpperCase() || 'UNKNOWN'}
              </span>

              {/* Mode */}
              <span className="text-text-secondary">Mode:</span>
              <span className={data.mode === 'live' ? 'text-green' : 'text-amber'}>
                {data.mode?.toUpperCase() || 'N/A'}
              </span>

              {/* Data Rows */}
              <span className="text-text-secondary">Data Rows:</span>
              <span className="text-text-primary">{data.data_rows}</span>

              {/* Integrity */}
              <span className="text-text-secondary">Integrity:</span>
              <span className={data.analyticalIntegrity === 'HEALTHY' ? 'text-green' : 'text-amber'}>
                {data.analyticalIntegrity}
              </span>

              {/* Models */}
              <span className="text-text-secondary">Models:</span>
              <span className="text-text-primary">{models.activeCount}/{models.total} active</span>
            </div>

            {/* Error Section */}
            {data.integrityErrors?.length > 0 && (
              <div className="text-red border-t border-border-subtle pt-1 mt-1">
                Errors: {data.integrityErrors.length}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default SystemStatusBadge;
