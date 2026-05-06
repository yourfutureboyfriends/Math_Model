// Section H — System Health
// API latency, error rates, and data freshness monitoring

import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Activity, AlertCircle, CheckCircle, Clock, Database } from 'lucide-react';

interface SystemHealthSectionProps {
  data?: {
    status?: string;
    apiLatency?: number;
    errorRate?: number;
    lastUpdate?: string;
    dataSources?: { name: string; status: string; latency: number }[];
  };
  performanceData?: {
    averageLatency?: number;
    p95Latency?: number;
    uptime?: number | string;
  };
}

export function SystemHealthSection({ data, performanceData }: SystemHealthSectionProps) {
  // FIXED: Add top-level null guard (Fix 7)
  if (!data) {
    return (
      <section id="system-health" className="terminal-section">
        <div className="section-header">
          <span className="section-tag">HEALTH</span>
          <h2 className="section-title">System Health</h2>
        </div>
        <div className="flex items-center gap-2 p-4">
          <div className="skeleton skeleton-text w-24" />
          <div className="skeleton skeleton-text w-16" />
        </div>
      </section>
    )
  }

  const getStatusColor = (status?: string) => {
    switch (status?.toLowerCase()) {
      case 'healthy':
        return 'text-green';
      case 'degraded':
        return 'text-amber';
      case 'critical':
        return 'text-red';
      default:
        return 'text-text-secondary';
    }
  };

  const getStatusIcon = (status?: string) => {
    switch (status?.toLowerCase()) {
      case 'healthy':
        return <CheckCircle className="w-4 h-4 text-green" />;
      case 'degraded':
        return <AlertCircle className="w-4 h-4 text-amber" />;
      case 'critical':
        return <AlertCircle className="w-4 h-4 text-red" />;
      default:
        return <Activity className="w-4 h-4 text-text-tertiary" />;
    }
  };

  const formatLatency = (ms?: number) => {
    if (ms === undefined) return '--';
    if (ms < 100) return `${ms.toFixed(0)}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  return (
    <section id="system-health" className="terminal-section">
      <div className="section-header">
        <span className="section-tag">HEALTH</span>
        <h2 className="section-title">System Health</h2>
        <Badge variant={data?.status === 'healthy' ? 'success' : 'neutral'} className="ml-2">
          {data?.status || 'Unknown'}
        </Badge>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Overall Status */}
        <Card className="p-4">
          <div className="flex items-center gap-3">
            {getStatusIcon(data?.status)}
            <div>
              <div className="text-2xs text-text-tertiary uppercase">Status</div>
              <div className={`font-mono font-medium ${getStatusColor(data?.status)}`}>
                {data?.status || 'Unknown'}
              </div>
            </div>
          </div>
        </Card>

        {/* API Latency */}
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <Clock className="w-4 h-4 text-bloomberg" />
            <div>
              <div className="text-2xs text-text-tertiary uppercase">API Latency</div>
              <div className="font-mono font-medium text-text-primary">
                {formatLatency(data?.apiLatency)}
              </div>
            </div>
          </div>
        </Card>

        {/* Error Rate */}
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <Activity className="w-4 h-4 text-text-secondary" />
            <div>
              <div className="text-2xs text-text-tertiary uppercase">Error Rate</div>
              <div className="font-mono font-medium text-text-primary">
                {data?.errorRate !== undefined ? `${(data.errorRate * 100).toFixed(2)}%` : '--'}
              </div>
            </div>
          </div>
        </Card>

        {/* Last Update */}
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <Database className="w-4 h-4 text-text-secondary" />
            <div>
              <div className="text-2xs text-text-tertiary uppercase">Last Update</div>
              <div className="font-mono font-medium text-text-primary">
                {data?.lastUpdate ? new Date(data.lastUpdate).toLocaleTimeString() : '--'}
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Data Sources Table */}
      {data?.dataSources && data.dataSources.length > 0 && (
        <Card title="Data Sources" className="mt-4">
          <div className="space-y-2">
            {data.dataSources.map((source) => (
              <div
                key={source.name}
                className="flex items-center justify-between p-2 border border-border-subtle bg-surface-2"
              >
                <div className="flex items-center gap-2">
                  {source.status === 'online' ? (
                    <CheckCircle className="w-3 h-3 text-green" />
                  ) : (
                    <AlertCircle className="w-3 h-3 text-red" />
                  )}
                  <span className="text-sm text-text-primary">{source.name}</span>
                </div>
                <div className="flex items-center gap-4">
                  <Badge variant={source.status === 'online' ? 'success' : 'danger'}>
                    {source.status}
                  </Badge>
                  <span className="text-xs text-text-tertiary font-mono">
                    {formatLatency(source.latency)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Performance Metrics */}
      {performanceData && (
        <Card title="Performance Metrics" className="mt-4">
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center">
              <div className="text-2xs text-text-tertiary uppercase mb-1">Avg Latency</div>
              <div className="font-mono text-lg text-text-primary">
                {formatLatency(performanceData.averageLatency)}
              </div>
            </div>
            <div className="text-center">
              <div className="text-2xs text-text-tertiary uppercase mb-1">P95 Latency</div>
              <div className="font-mono text-lg text-text-primary">
                {formatLatency(performanceData.p95Latency)}
              </div>
            </div>
            <div className="text-center">
              <div className="text-2xs text-text-tertiary uppercase mb-1">Uptime</div>
              <div className="font-mono text-lg text-text-primary">
                {performanceData.uptime !== undefined
                  ? (typeof performanceData.uptime === 'number'
                      ? `${performanceData.uptime.toFixed(2)}%`
                      : performanceData.uptime)
                  : '--'}
              </div>
            </div>
          </div>
        </Card>
      )}
    </section>
  );
}
