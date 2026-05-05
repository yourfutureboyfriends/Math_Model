// Phase 8 Terminal Topbar
// 48px fixed, institutional aesthetic

import { Command, Download, Maximize, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface TopbarProps {
  latestDate?: string;
  dataStatus?: 'current' | 'acceptable' | 'stale' | 'unknown';
  mode?: string;
  alertCount?: number;
  onRefresh?: () => void;
  loading?: boolean;
  onCommandPalette?: () => void;
  onAlertsPanel?: () => void;
}

export function Topbar({
  latestDate,
  dataStatus = 'unknown',
  mode = 'unknown',
  alertCount = 0,
  onCommandPalette,
  onAlertsPanel,
}: TopbarProps) {
  const getStatusColor = () => {
    switch (dataStatus) {
      case 'current':
        return 'bg-accent';
      case 'acceptable':
        return 'bg-amber';
      case 'stale':
        return 'bg-red';
      default:
        return 'bg-text-tertiary';
    }
  };

  const formatTimeAgo = (dateStr?: string) => {
    if (!dateStr) return 'Unknown';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const seconds = Math.floor(diffMs / 1000);
    const minutes = Math.floor(diffMs / 60000);
    const hours = Math.floor(diffMs / 3600000);

    // CRITICAL FIX: Never show days - show stale warning instead
    if (seconds < 60) return `${seconds}s ago`;  // Show seconds when < 1 min
    if (minutes < 60) return `${minutes}m ago`;    // Show minutes when < 1 hour
    if (hours < 24) return `${hours}h ago`;        // Show hours when < 24 hours
    return '⚠️ Stale data';                         // Warning when > 24 hours
  };

  return (
    <header className="fixed top-0 left-0 right-0 h-12 bg-surface-2 border-b border-border z-50">
      <div className="h-full flex items-center justify-between px-4">
        {/* Left: Platform ID */}
        <div className="flex items-center gap-3">
          <button className="flex items-center gap-2 text-text-secondary hover:text-text-primary transition-colors">
            <span className="font-mono text-sm">▸</span>
            <span className="font-mono text-sm tracking-tight">MACRO TERMINAL</span>
          </button>
          <span className="text-text-tertiary text-2xs font-mono">v8.0</span>
        </div>

        {/* Center: Live Status + Timestamp */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <span className={cn('w-2 h-2 rounded-full live-dot', getStatusColor())} />
            <span className="text-xs font-medium text-text-secondary uppercase tracking-wider">
              {dataStatus === 'current' ? 'Live' : dataStatus === 'acceptable' ? 'Cached' : dataStatus === 'stale' ? 'Stale' : 'Unknown'}
            </span>
          </div>

          {latestDate && (
            <>
              <span className="text-xs text-text-secondary font-mono">{latestDate}</span>
              <span className="text-xs text-text-tertiary font-mono">Refreshed {formatTimeAgo(latestDate)}</span>
            </>
          )}

          <span className="text-2xs font-mono text-text-tertiary uppercase">
            {mode}
          </span>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2">
          {/* Health indicator */}
          <div className="flex items-center gap-1.5 px-2 py-1">
            <span className="w-1.5 h-1.5 rounded-full bg-accent" />
            <span className="text-2xs text-text-tertiary">health</span>
          </div>

          {/* Alerts button */}
          {alertCount > 0 && (
            <button
              onClick={onAlertsPanel}
              className="flex items-center gap-1.5 px-2 py-1 rounded-sm border border-amber/30 bg-amber-dim text-amber text-xs font-medium hover:bg-amber/20 transition-colors"
            >
              <AlertTriangle className="w-3 h-3" />
              <span>{alertCount} alerts</span>
            </button>
          )}

          {/* Export */}
          <button className="icon-btn" title="Export PDF">
            <Download className="w-4 h-4" />
          </button>

          {/* Command palette trigger */}
          <button
            onClick={onCommandPalette}
            className="flex items-center gap-1 px-2 py-1 rounded-sm border border-border text-text-secondary hover:border-border-strong hover:text-text-primary transition-colors"
          >
            <Command className="w-3 h-3" />
            <span className="text-xs font-mono">K</span>
          </button>

          {/* Fullscreen */}
          <button className="icon-btn" title="Fullscreen">
            <Maximize className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
