// UPGRADE-5: Signal Alert System — Hedge Fund Grade Alerting
// Enhanced with sound notifications, action buttons, and real-time triggers

import { useState, useEffect, useCallback, useRef } from 'react';
import { AlertItem, AlertsData } from '@/types';
import { X, AlertCircle, AlertTriangle, Info, Volume2, VolumeX, BellRing } from 'lucide-react';

interface AlertsBannerProps {
  alerts?: AlertsData;
  onAcknowledge?: (alertId: string) => void;
  onAction?: (action: string) => void;
  soundEnabled?: boolean;
}

export function AlertsBanner({ alerts, onAcknowledge, onAction, soundEnabled = true }: AlertsBannerProps) {
  const [dismissedAlerts, setDismissedAlerts] = useState<Set<string>>(new Set());
  const [audioEnabled, setAudioEnabled] = useState(soundEnabled);
  const [hasInteracted, setHasInteracted] = useState(false);
  const prevAlertIds = useRef<Set<string>>(new Set());
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Initialize audio on first user interaction
  useEffect(() => {
    const initAudio = () => {
      if (!audioRef.current) {
        // Create audio context for beep sound
        const AudioContext = window.AudioContext || (window as any).webkitAudioContext;
        if (AudioContext) {
          const ctx = new AudioContext();
          audioRef.current = { play: () => playBeep(ctx) } as any;
        }
      }
      setHasInteracted(true);
    };

    window.addEventListener('click', initAudio, { once: true });
    window.addEventListener('keydown', initAudio, { once: true });

    return () => {
      window.removeEventListener('click', initAudio);
      window.removeEventListener('keydown', initAudio);
    };
  }, []);

  // Play sound when new critical/warning alerts appear
  useEffect(() => {
    if (!alerts?.active || !audioEnabled || !hasInteracted) return;

    const currentAlertIds = new Set(alerts.active.map(a => a.id));
    const newAlerts = alerts.active.filter(a => !prevAlertIds.current.has(a.id));

    // Play sound if there are new critical or warning alerts
    const hasNewImportant = newAlerts.some(a => a.severity === 'critical' || a.severity === 'warning');
    if (hasNewImportant && audioRef.current) {
      audioRef.current.play();
    }

    prevAlertIds.current = currentAlertIds;
  }, [alerts, audioEnabled, hasInteracted]);

  const playBeep = useCallback((ctx: AudioContext) => {
    const oscillator = ctx.createOscillator();
    const gainNode = ctx.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(ctx.destination);

    oscillator.frequency.value = 800;
    oscillator.type = 'sine';

    gainNode.gain.setValueAtTime(0.1, ctx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);

    oscillator.start(ctx.currentTime);
    oscillator.stop(ctx.currentTime + 0.3);
  }, []);

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
    ? 'bg-red-dim border-red'
    : hasWarning
    ? 'bg-amber-dim border-amber'
    : 'bg-surface-1 border-border';

  return (
    <div className={`w-full ${bannerClass} border-b sticky top-0 z-50`}>
      {/* Audio Toggle */}
      <div className="max-w-[1920px] mx-auto flex items-center">
        <div className="flex-shrink-0 px-2 border-r border-white/10">
          <button
            onClick={() => setAudioEnabled(!audioEnabled)}
            className="p-1.5 rounded hover:bg-white/10 transition-colors"
            title={audioEnabled ? 'Disable alert sounds' : 'Enable alert sounds'}
          >
            {audioEnabled ? (
              <Volume2 className="w-4 h-4 text-white/70" />
            ) : (
              <VolumeX className="w-4 h-4 text-white/40" />
            )}
          </button>
        </div>

        {/* Alert Count Badge */}
        <div className="flex-shrink-0 px-3 border-r border-white/10">
          <div className="flex items-center gap-1.5">
            <BellRing className="w-4 h-4 text-white/70" />
            <span className="text-xs text-white font-medium">
              {sortedAlerts.length} Active
            </span>
            {hasCritical && (
              <span className="px-1.5 py-0.5 text-2xs bg-red text-bg font-bold">
                CRIT
              </span>
            )}
          </div>
        </div>

        {/* Alerts */}
        <div className="flex-1 overflow-hidden">
          {sortedAlerts.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              onDismiss={() => handleDismiss(alert.id)}
              onAction={onAction}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

interface AlertRowProps {
  alert: AlertItem;
  onDismiss: () => void;
  onAction?: (action: string) => void;
}

function AlertRow({ alert, onDismiss, onAction }: AlertRowProps) {
  const severityConfig = {
    critical: {
      icon: AlertCircle,
      iconClass: 'text-red',
      bgClass: 'bg-red-dim',
      borderClass: 'border-red',
      pulse: true,
    },
    warning: {
      icon: AlertTriangle,
      iconClass: 'text-amber',
      bgClass: 'bg-amber-dim',
      borderClass: 'border-amber',
      pulse: false,
    },
    info: {
      icon: Info,
      iconClass: 'text-blue',
      bgClass: 'bg-blue-dim',
      borderClass: 'border-blue',
      pulse: false,
    },
  };

  const config = severityConfig[alert.severity];
  const Icon = config.icon;

  // UPGRADE-5: Compact inline alert with action buttons
  return (
    <div
      className={`flex items-center gap-2 px-3 py-1.5 ${config.bgClass} border ${config.borderClass} rounded-sm`}
    >
      {/* Severity Icon */}
      <div className={`flex-shrink-0 ${config.pulse ? 'animate-pulse' : ''}`}>
        <Icon className={`w-3.5 h-3.5 ${config.iconClass}`} />
      </div>

      {/* Alert Message */}
      <p className="text-xs text-white font-medium truncate max-w-[200px]">
        {alert.message}
      </p>

      {/* Action Button */}
      {alert.action && (
        <button
          onClick={() => onAction?.(alert.action)}
          className="flex-shrink-0 px-2 py-0.5 text-2xs font-medium bg-white/10 text-white rounded hover:bg-white/20 transition-colors"
        >
          {alert.action}
        </button>
      )}

      {/* Value Indicator */}
      <div className="hidden md:flex items-center gap-1 text-2xs text-white/40 flex-shrink-0">
        <span>{alert.currentValue}</span>
      </div>

      {/* Dismiss */}
      <button
        onClick={onDismiss}
        className="flex-shrink-0 p-0.5 rounded hover:bg-white/10 transition-colors opacity-70 hover:opacity-100"
        aria-label="Dismiss"
      >
        <X className="w-3 h-3 text-white" />
      </button>
    </div>
  );
}
