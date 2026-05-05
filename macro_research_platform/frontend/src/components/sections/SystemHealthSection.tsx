// Phase 8 — System Health Dashboard Section (Redesigned)
// System status with terminal aesthetic

import {
  Activity,
  Server,
  Database,
  Clock,
  AlertTriangle,
  CheckCircle,
  XCircle
} from 'lucide-react';
import type { PerformanceTrackingData } from '@/types';

interface HealthStatus {
  component: string;
  status: 'healthy' | 'degraded' | 'down' | 'unknown';
  latency?: number;
  lastCheck?: string;
  message?: string;
}

interface SystemHealthData {
  overallStatus: 'healthy' | 'degraded' | 'critical' | 'unknown';
  apiStatus: HealthStatus;
  modelStatus: HealthStatus;
  dataPipeline: HealthStatus;
  cacheStatus: HealthStatus;
  uptime: string;
  version: string;
  activeModels: number;
  totalModels: number;
  lastPrediction: string;
  errorRate: number;
  avgLatency: number;
}

interface SystemHealthSectionProps {
  data?: SystemHealthData;
  performanceData?: PerformanceTrackingData;
}

export function SystemHealthSection({ data, performanceData }: SystemHealthSectionProps) {
  const healthData: SystemHealthData = data || {
    overallStatus: 'healthy',
    apiStatus: { component: 'API Server', status: 'healthy', latency: 45 },
    modelStatus: { component: 'ML Models', status: 'healthy', message: '15 models active' },
    dataPipeline: { component: 'Data Pipeline', status: 'healthy', lastCheck: new Date().toISOString() },
    cacheStatus: { component: 'Cache', status: 'healthy', message: 'Memory cache active' },
    uptime: '99.9%',
    version: 'v2.8.0',
    activeModels: 15,
    totalModels: 15,
    lastPrediction: new Date().toISOString(),
    errorRate: 0.01,
    avgLatency: 125
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'text-green';
      case 'degraded':
        return 'text-amber';
      case 'critical':
      case 'down':
        return 'text-red';
      default:
        return 'text-text-tertiary';
    }
  };

  const getStatusBg = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'bg-green-dim border-green';
      case 'degraded':
        return 'bg-amber-dim border-amber';
      case 'critical':
      case 'down':
        return 'bg-red-dim border-red';
      default:
        return 'bg-surface-1 border-border';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return CheckCircle;
      case 'degraded':
        return AlertTriangle;
      case 'critical':
      case 'down':
        return XCircle;
      default:
        return Activity;
    }
  };

  const getStatusTag = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'signal-tag bullish';
      case 'degraded':
        return 'signal-tag warning';
      case 'critical':
      case 'down':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  const StatusRow = ({ status }: { status: HealthStatus }) => {
    const Icon = getStatusIcon(status.status);
    return (
      <div className="flex items-center justify-between py-2 border-b border-border-subtle last:border-b-0">
        <div className="flex items-center gap-2">
          <Icon className={`w-3 h-3 ${getStatusColor(status.status)}`} />
          <span className="text-xs text-text-primary">{status.component}</span>
        </div>
        <div className="flex items-center gap-3">
          {status.latency && (
            <span className="text-2xs text-text-tertiary">{status.latency}ms</span>
          )}
          {status.message && (
            <span className="text-2xs text-text-secondary hidden sm:inline">{status.message}</span>
          )}
          <span className={getStatusTag(status.status)}>
            {status.status.toUpperCase()}
          </span>
        </div>
      </div>
    );
  };

  const OverallStatusIcon = getStatusIcon(healthData.overallStatus);

  return (
    <div id="system-health" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">22</span>
          <h2 className="section-title">System Health</h2>
          <span className={`section-meta ${getStatusColor(healthData.overallStatus)}`}>
            {healthData.overallStatus.toUpperCase()}
          </span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Overall Status Header */}
        <div className={`p-3 border ${getStatusBg(healthData.overallStatus)}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <OverallStatusIcon className={`w-5 h-5 ${getStatusColor(healthData.overallStatus)}`} />
              <div>
                <div className="text-xs font-medium text-text-primary">
                  {healthData.overallStatus.toUpperCase()}
                </div>
                <div className="text-2xs text-text-tertiary">
                  {healthData.version} • Uptime {healthData.uptime}
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider">Models</div>
              <div className="text-lg font-mono font-bold text-text-primary">
                {healthData.activeModels}/{healthData.totalModels}
              </div>
            </div>
          </div>
        </div>

        {/* Component Status Grid */}
        <div className="p-3 bg-surface-1 border border-border">
          <StatusRow status={healthData.apiStatus} />
          <StatusRow status={healthData.modelStatus} />
          <StatusRow status={healthData.dataPipeline} />
          <StatusRow status={healthData.cacheStatus} />
        </div>

        {/* Performance Metrics */}
        <div className="grid grid-cols-3 gap-2">
          <div className="p-2 bg-surface-1 border border-border text-center">
            <div className="flex items-center justify-center gap-1 text-2xs text-text-tertiary mb-0.5">
              <Clock className="w-3 h-3" />
              <span>Latency</span>
            </div>
            <div className="text-sm font-mono font-bold text-text-primary">
              {healthData.avgLatency}ms
            </div>
          </div>

          <div className="p-2 bg-surface-1 border border-border text-center">
            <div className="flex items-center justify-center gap-1 text-2xs text-text-tertiary mb-0.5">
              <AlertTriangle className="w-3 h-3" />
              <span>Errors</span>
            </div>
            <div className={`text-sm font-mono font-bold ${healthData.errorRate > 0.05 ? 'text-red' : 'text-green'}`}>
              {(healthData.errorRate * 100).toFixed(2)}%
            </div>
          </div>

          <div className="p-2 bg-surface-1 border border-border text-center">
            <div className="flex items-center justify-center gap-1 text-2xs text-text-tertiary mb-0.5">
              <Activity className="w-3 h-3" />
              <span>Predictions</span>
            </div>
            <div className="text-sm font-mono font-bold text-text-primary">
              {performanceData?.totalPredictions || '—'}
            </div>
          </div>
        </div>

        {/* Model Health Summary */}
        {performanceData?.modelAccuracies && (
          <div className="p-3 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">
              Model Accuracy
            </div>
            <div className="grid grid-cols-5 gap-2">
              {Object.entries(performanceData.modelAccuracies)
                .slice(0, 5)
                .map(([model, accuracy]) => (
                  <div key={model} className="text-center">
                    <div className="text-2xs text-text-secondary truncate" title={model}>
                      {model.slice(0, 6)}
                    </div>
                    <div className={`text-xs font-mono font-bold ${
                      (accuracy || 0) >= 0.6 ? 'text-green' :
                      (accuracy || 0) >= 0.45 ? 'text-amber' : 'text-red'
                    }`}>
                      {accuracy !== null ? `${(accuracy * 100).toFixed(0)}%` : 'N/A'}
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Last Updated */}
        <div className="flex items-center justify-between text-2xs text-text-tertiary">
          <div className="flex items-center gap-2">
            <Database className="w-3 h-3" />
            <span>Last: {new Date(healthData.lastPrediction).toLocaleTimeString()}</span>
          </div>
          <div className="flex items-center gap-2">
            <Server className="w-3 h-3" />
            <span>Operational</span>
          </div>
        </div>
      </div>
    </div>
  );
}
