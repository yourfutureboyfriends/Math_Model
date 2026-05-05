// Bloomberg Terminal Topbar — 64px total (40px main + 24px ticker)
// Row 1: Branding | Function keys | Session badges | Data status | Time | Tools
// Row 2: Market ticker strip

import { useState, useEffect } from 'react';
import { Download, Maximize, AlertTriangle, LayoutGrid, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';

interface TickerItem {
  sym: string;
  val?: number | string;
  chg?: number;
  pct?: number;
}

interface TopbarProps {
  latestDate?: string;
  dataStatus?: 'current' | 'acceptable' | 'stale' | 'unknown';
  mode?: string;
  alertCount?: number;
  onRefresh?: () => void;
  loading?: boolean;
  onCommandPalette?: () => void;
  onAlertsPanel?: () => void;
  currentRegime?: string;
  data?: any;
}

// Derive market session status from current UTC time
function getSessionStatus(): { us: 'open' | 'pre' | 'closed'; eu: 'open' | 'closed'; as: 'open' | 'closed' } {
  const now = new Date();
  const utcH = now.getUTCHours();
  const utcM = now.getUTCMinutes();
  const utcMin = utcH * 60 + utcM;
  const day = now.getUTCDay(); // 0=Sun, 6=Sat

  const isWeekday = day >= 1 && day <= 5;

  return {
    // NYSE: 14:30–21:00 UTC; pre: 09:00–14:30 UTC
    us: !isWeekday ? 'closed'
      : utcMin >= 870 && utcMin < 1260 ? 'open'
      : utcMin >= 540 && utcMin < 870  ? 'pre'
      : 'closed',
    // LSE: 08:00–16:30 UTC
    eu: !isWeekday ? 'closed'
      : utcMin >= 480 && utcMin < 990  ? 'open'
      : 'closed',
    // TSE: 00:00–06:00 UTC (approx)
    as: !isWeekday ? 'closed'
      : utcMin >= 0 && utcMin < 360    ? 'open'
      : 'closed',
  };
}

// Extract ticker data from dashboard response
function buildTicker(data?: any): TickerItem[] {
  const km = data?.keyMetrics;
  const ri = data?.riskIndicators;
  // const liq = data?.liquidity;  // Reserved for liquidity ticker display

  return [
    {
      sym: 'SPX',
      val: km?.spxLevel   ? Number(km.spxLevel).toFixed(0)   : undefined,
      chg: km?.spxChange  ? Number(km.spxChange)              : undefined,
      pct: km?.spxChangePct ? Number(km.spxChangePct)         : undefined,
    },
    {
      sym: 'NDX',
      val: km?.ndxLevel   ? Number(km.ndxLevel).toFixed(0)   : undefined,
      pct: km?.ndxChangePct ? Number(km.ndxChangePct)        : undefined,
    },
    {
      sym: 'VIX',
      val: ri?.vix        ? Number(ri.vix).toFixed(1)        : undefined,
      chg: ri?.vixChange  ? Number(ri.vixChange)             : undefined,
    },
    {
      sym: '10Y',
      val: km?.tenYearYield ? (Number(km.tenYearYield) * 100).toFixed(2) + '%' : undefined,
      chg: km?.tenYearChange ? Number(km.tenYearChange)      : undefined,
    },
    {
      sym: '2Y',
      val: km?.twoYearYield ? (Number(km.twoYearYield) * 100).toFixed(2) + '%' : undefined,
    },
    {
      sym: 'DXY',
      val: km?.dxy         ? Number(km.dxy).toFixed(2)       : undefined,
      pct: km?.dxyChangePct ? Number(km.dxyChangePct)        : undefined,
    },
    {
      sym: 'EUR/USD',
      val: km?.eurusd      ? Number(km.eurusd).toFixed(4)    : undefined,
      pct: km?.eurusdChangePct ? Number(km.eurusdChangePct)  : undefined,
    },
    {
      sym: 'GLD',
      val: km?.gold        ? Number(km.gold).toFixed(0)      : undefined,
      pct: km?.goldChangePct ? Number(km.goldChangePct)      : undefined,
    },
    {
      sym: 'WTI',
      val: km?.oil         ? Number(km.oil).toFixed(2)       : undefined,
      pct: km?.oilChangePct ? Number(km.oilChangePct)       : undefined,
    },
    {
      sym: 'FED',
      val: km?.fedRate     ? (Number(km.fedRate) * 100).toFixed(2) + '%' : undefined,
    },
  ];
}

const FN_KEYS = [
  { n: 'F1', label: 'OVERVIEW',  section: 'master-signal' },
  { n: 'F2', label: 'SIGNALS',   section: 'signals' },
  { n: 'F3', label: 'RISK',      section: 'risk-indicators' },
  { n: 'F4', label: 'FORECASTS', section: 'nowcast' },
  { n: 'F5', label: 'STRATEGY',  section: 'gmo-forecasts' },
  { n: 'F6', label: 'PORTFOLIO', section: 'portfolio' },
  { n: 'F7', label: 'SYSTEM',    section: 'system-health' },
];

export function Topbar({
  latestDate,
  dataStatus = 'unknown',
  mode = 'LIVE',
  alertCount = 0,
  onRefresh,
  loading,
  onCommandPalette,
  onAlertsPanel,
  data,
}: TopbarProps) {
  const [downloading, setDownloading] = useState(false);
  const [isCompact, setIsCompact] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [sessions, setSessions] = useState(getSessionStatus());

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
      setSessions(getSessionStatus());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Restore density preference
  useEffect(() => {
    const density = new URL(window.location.href).searchParams.get('density');
    if (density === 'compact') {
      setIsCompact(true);
      document.documentElement.setAttribute('data-density', 'compact');
    }
  }, []);

  const toggleCompact = () => {
    const next = !isCompact;
    setIsCompact(next);
    document.documentElement.setAttribute('data-density', next ? 'compact' : 'comfortable');
    const url = new URL(window.location.href);
    next ? url.searchParams.set('density', 'compact') : url.searchParams.delete('density');
    window.history.replaceState({}, '', url);
  };

  const handleExportPDF = async () => {
    try {
      setDownloading(true);
      const res = await fetch('/api/report/generate?type=full');
      if (!res.ok) throw new Error('Failed');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = Object.assign(document.createElement('a'), {
        href: url,
        download: `macro_report_${new Date().toISOString().split('T')[0]}.pdf`,
      });
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch {
      alert('Failed to generate PDF report');
    } finally {
      setDownloading(false);
    }
  };

  const navigateTo = (section: string) => {
    document.getElementById(section)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const statusDot =
    dataStatus === 'current'    ? 'bg-green'     :
    dataStatus === 'acceptable' ? 'bg-amber'     :
    dataStatus === 'stale'      ? 'bg-red'       : 'bg-text-tertiary';

  const statusLabel =
    dataStatus === 'current'    ? 'LIVE'     :
    dataStatus === 'acceptable' ? 'CACHED'   :
    dataStatus === 'stale'      ? 'STALE'    : 'UNK';

  const timeStr = currentTime.toISOString().split('T')[1].split('.')[0];
  const dateStr = currentTime.toISOString().split('T')[0];

  const ticker = buildTicker(data);

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-surface-2 border-b border-border"
            style={{ height: 'var(--topbar-height)' }}>

      {/* ── ROW 1: Main bar (40px) ─────────────────────────────────────────────── */}
      <div className="topbar-main-row">

        {/* Branding */}
        <div className="flex items-center gap-2 mr-2 shrink-0">
          <span className="font-mono text-bloomberg font-bold tracking-tight" style={{ fontSize: 13 }}>▸</span>
          <span className="font-mono text-text-primary font-bold tracking-tight" style={{ fontSize: 12, letterSpacing: '0.06em' }}>
            MACRO OS
          </span>
          <span className="font-mono text-text-tertiary" style={{ fontSize: 10 }}>v8.0</span>
        </div>

        <div className="topbar-divider" />

        {/* Bloomberg function keys */}
        <div className="hidden xl:flex items-center gap-1">
          {FN_KEYS.map((k) => (
            <button key={k.n} className="fn-key" onClick={() => navigateTo(k.section)}>
              <span className="fn-key-num">{k.n}</span>
              <span>{k.label}</span>
            </button>
          ))}
        </div>

        <div className="hidden xl:block topbar-divider" />

        {/* Market sessions */}
        <div className="hidden lg:flex items-center gap-1.5">
          <span className={cn('session-badge', sessions.us)}>
            <span className={cn('w-1.5 h-1.5 rounded-full shrink-0',
              sessions.us === 'open' ? 'bg-green' :
              sessions.us === 'pre'  ? 'bg-amber' : 'bg-text-tertiary'
            )} />
            US {sessions.us === 'pre' ? 'PRE' : sessions.us === 'open' ? 'OPEN' : 'CLOSED'}
          </span>
          <span className={cn('session-badge', sessions.eu)}>
            <span className={cn('w-1.5 h-1.5 rounded-full shrink-0',
              sessions.eu === 'open' ? 'bg-green' : 'bg-text-tertiary'
            )} />
            EU {sessions.eu === 'open' ? 'OPEN' : 'CLOSED'}
          </span>
          <span className={cn('session-badge', sessions.as)}>
            <span className={cn('w-1.5 h-1.5 rounded-full shrink-0',
              sessions.as === 'open' ? 'bg-green' : 'bg-text-tertiary'
            )} />
            AS {sessions.as === 'open' ? 'OPEN' : 'CLOSED'}
          </span>
        </div>

        <div className="hidden lg:block topbar-divider" />

        {/* Data status */}
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={cn('w-1.5 h-1.5 rounded-full live-dot', statusDot)} />
          <span className="font-mono text-text-secondary" style={{ fontSize: 10, letterSpacing: '0.06em' }}>
            {statusLabel}
          </span>
          {latestDate && (
            <span className="hidden md:inline font-mono text-text-tertiary" style={{ fontSize: 10 }}>
              {latestDate}
            </span>
          )}
        </div>

        <div className="topbar-divider" />

        {/* Clock */}
        <div className="hidden md:flex items-center gap-2 px-2 border border-border bg-surface-1 shrink-0"
             style={{ height: 22 }}>
          <span className="w-1 h-1 rounded-full bg-bloomberg animate-pulse shrink-0" />
          <span className="font-mono text-text-secondary" style={{ fontSize: 10 }}>
            {dateStr}
          </span>
          <span className="font-mono text-text-primary font-semibold" style={{ fontSize: 10 }}>
            {timeStr} UTC
          </span>
        </div>

        {/* Mode badge */}
        <div className="ml-auto flex items-center gap-1 shrink-0">
          <span className="font-mono text-bloomberg bg-bloomberg-muted border border-bloomberg-border px-2 py-0.5"
                style={{ fontSize: 10, letterSpacing: '0.08em' }}>
            {mode}
          </span>
        </div>

        {/* Alerts */}
        {alertCount > 0 && (
          <button
            onClick={onAlertsPanel}
            className="flex items-center gap-1 px-2 border border-amber/30 bg-amber-dim text-amber hover:bg-amber/20 transition-colors shrink-0"
            style={{ height: 22, fontSize: 10 }}
          >
            <AlertTriangle className="w-3 h-3" />
            <span className="font-mono">{alertCount}</span>
          </button>
        )}

        {/* Tool buttons */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={onRefresh}
            disabled={loading}
            className="icon-btn"
            style={{ width: 26, height: 26 }}
            title="Refresh data"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
          </button>

          <button
            onClick={handleExportPDF}
            disabled={downloading}
            className="icon-btn"
            style={{ width: 26, height: 26 }}
            title="Export PDF"
          >
            <Download className={cn('w-3.5 h-3.5', downloading && 'animate-pulse')} />
          </button>

          <button
            onClick={onCommandPalette}
            className="flex items-center gap-1 border border-border text-text-secondary hover:border-bloomberg-border hover:text-bloomberg transition-colors px-2"
            style={{ height: 26, fontSize: 10 }}
            title="Command palette (⌘K)"
          >
            <span className="font-mono">⌘K</span>
          </button>

          <button
            onClick={toggleCompact}
            className={cn(
              'flex items-center gap-1 px-2 border font-mono transition-colors hidden lg:flex',
              isCompact
                ? 'border-bloomberg-border bg-bloomberg-muted text-bloomberg'
                : 'border-border text-text-secondary hover:border-bloomberg-border hover:text-bloomberg'
            )}
            style={{ height: 26, fontSize: 10 }}
            title={isCompact ? 'Comfortable mode' : 'Compact mode'}
          >
            <LayoutGrid className="w-3 h-3" />
            {isCompact ? 'COMPACT' : 'COZY'}
          </button>

          <button
            className="icon-btn"
            style={{ width: 26, height: 26 }}
            title="Fullscreen"
            onClick={() => {
              if (!document.fullscreenElement) document.documentElement.requestFullscreen();
              else document.exitFullscreen();
            }}
          >
            <Maximize className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* ── ROW 2: Market ticker strip (24px) ─────────────────────────────────── */}
      <div className="ticker-strip">
        {ticker.map((item) => (
          <div key={item.sym} className="ticker-item">
            <span className="ticker-sym">{item.sym}</span>
            {item.val !== undefined ? (
              <span className="ticker-val">{item.val}</span>
            ) : (
              <span className="ticker-val text-text-tertiary">—</span>
            )}
            {item.pct !== undefined ? (
              <span className={item.pct >= 0 ? 'ticker-chg-pos' : 'ticker-chg-neg'}>
                {item.pct >= 0 ? '+' : ''}{item.pct.toFixed(2)}%
              </span>
            ) : item.chg !== undefined ? (
              <span className={item.chg >= 0 ? 'ticker-chg-pos' : 'ticker-chg-neg'}>
                {item.chg >= 0 ? '+' : ''}{item.chg.toFixed(2)}
              </span>
            ) : null}
          </div>
        ))}

        {/* Regime label at far right of ticker */}
        <div className="ml-auto flex items-center px-3 shrink-0 border-l border-border-subtle h-full gap-2">
          <span className="font-mono text-text-tertiary" style={{ fontSize: 9, letterSpacing: '0.06em' }}>REGIME</span>
          <span className="font-mono text-bloomberg font-bold" style={{ fontSize: 10, letterSpacing: '0.06em' }}>
            {data?.regime?.current?.toUpperCase() ?? '—'}
          </span>
        </div>
      </div>
    </header>
  );
}
