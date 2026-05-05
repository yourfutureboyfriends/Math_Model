import { Activity, RefreshCw, Terminal } from 'lucide-react';
import { cn } from '@/lib/utils';

interface HeaderProps {
  latestDate?: string;
  dataStatus?: 'current' | 'acceptable' | 'stale' | 'unknown';
  mode?: string;
  onRefresh?: () => void;
  loading?: boolean;
}

const statusColors = {
  current: 'text-accent-green',
  acceptable: 'text-accent-amber',
  stale: 'text-accent-red',
  unknown: 'text-text-muted',
};

export function Header({
  latestDate,
  dataStatus = 'unknown',
  mode = 'unknown',
  onRefresh,
  loading,
}: HeaderProps) {
  return (
    <header className="bg-terminal-card border-b border-terminal-border px-6 py-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-terminal-elevated rounded-lg">
            <Terminal className="w-6 h-6 text-accent-amber" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-text-primary tracking-tight">
              Macro Research Platform
            </h1>
            <p className="text-xs text-text-muted">
              Multi-Model Macro Regime Classification System
            </p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          {/* Data Status */}
          <div className="flex items-center gap-2 text-sm">
            <Activity className={cn('w-4 h-4', statusColors[dataStatus])} />
            <span className="text-text-secondary">Data:</span>
            <span className={cn('font-mono font-medium', statusColors[dataStatus])}>
              {dataStatus === 'current' && 'Live'}
              {dataStatus === 'acceptable' && 'Cached'}
              {dataStatus === 'stale' && 'Stale'}
              {dataStatus === 'unknown' && 'Unknown'}
            </span>
          </div>

          {/* Latest Date */}
          {latestDate && (
            <div className="text-sm">
              <span className="text-text-secondary">Latest:</span>
              <span className="font-mono text-text-primary ml-2">{latestDate}</span>
            </div>
          )}

          {/* Mode Badge */}
          <div className="px-3 py-1 bg-terminal-elevated border border-terminal-border rounded text-xs font-medium">
            <span className="text-text-muted">Mode:</span>
            <span className={cn(
              'ml-2 font-mono',
              mode === 'live' ? 'text-accent-green' : 'text-accent-amber'
            )}>
              {mode.toUpperCase()}
            </span>
          </div>

          {/* Refresh Button */}
          <button
            onClick={onRefresh}
            disabled={loading}
            className={cn(
              'p-2 bg-terminal-elevated border border-terminal-border rounded',
              'text-text-secondary hover:text-text-primary hover:border-terminal-border-light',
              'transition-all duration-150',
              loading && 'animate-spin opacity-50'
            )}
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
