// Phase 12 Task 3 — Notification Settings Panel
// Configure Email, Slack, Browser notifications and alert thresholds

import { useState, useEffect } from 'react';
import { Bell, Mail, MessageSquare, Smartphone, Clock, Check, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface NotificationConfig {
  email_enabled: boolean;
  slack_enabled: boolean;
  browser_enabled: boolean;
  thresholds: {
    recession_risk: number;
    vix: number;
    anomaly_score: number;
    hy_spreads: number;
    geo_risk: number;
    options_fear: number;
    options_greed: number;
  };
  quiet_hours: {
    enabled: boolean;
    start: number;
    end: number;
  };
}

const defaultConfig: NotificationConfig = {
  email_enabled: false,
  slack_enabled: false,
  browser_enabled: true,
  thresholds: {
    recession_risk: 30,
    vix: 35,
    anomaly_score: 0.75,
    hy_spreads: 400,
    geo_risk: 1.5,
    options_fear: 70,
    options_greed: 15,
  },
  quiet_hours: {
    enabled: true,
    start: 22,
    end: 7,
  },
};

export function NotificationSettings() {
  const [isOpen, setIsOpen] = useState(false);
  const [config, setConfig] = useState<NotificationConfig>(defaultConfig);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, boolean> | null>(null);

  // Load config on mount
  useEffect(() => {
    fetchConfig();
    checkNotificationPermission();
  }, []);

  const fetchConfig = async () => {
    try {
      const response = await fetch('/api/alerts/config');
      if (response.ok) {
        const data = await response.json();
        setConfig({
          ...defaultConfig,
          ...data.config,
        });
      }
    } catch (error) {
      // Load error handled silently
    }
  };

  const checkNotificationPermission = async () => {
    if ('Notification' in window) {
      const permission = await Notification.requestPermission();
      setConfig((prev) => ({
        ...prev,
        browser_enabled: permission === 'granted',
      }));
    }
  };

  const saveConfig = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('/api/alerts/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });

      if (response.ok) {
        setIsSaved(true);
        setTimeout(() => setIsSaved(false), 2000);
      }
    } catch (error) {
      // Save error handled silently
    } finally {
      setIsLoading(false);
    }
  };

  const testChannels = async () => {
    setIsLoading(true);
    setTestResults(null);
    try {
      const response = await fetch('/api/alerts/test?channel=all', {
        method: 'POST',
      });
      if (response.ok) {
        const data = await response.json();
        setTestResults(data.results);
      }
    } catch (error) {
      // Test error handled silently
    } finally {
      setIsLoading(false);
    }
  };

  const requestBrowserPermission = async () => {
    if (!('Notification' in window)) {
      alert('Browser notifications not supported');
      return;
    }

    const permission = await Notification.requestPermission();
    setConfig((prev) => ({
      ...prev,
      browser_enabled: permission === 'granted',
    }));
  };

  const updateThreshold = (key: keyof NotificationConfig['thresholds'], value: number) => {
    setConfig((prev) => ({
      ...prev,
      thresholds: {
        ...prev.thresholds,
        [key]: value,
      },
    }));
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-2 px-3 py-1.5 bg-surface-2 border border-border-subtle rounded text-xs font-medium text-text-secondary hover:bg-surface-3 hover:text-text-primary transition-colors"
      >
        <Bell className="w-3 h-3" />
        <span>Settings</span>
      </button>
    );
  }

  return (
    <div className="fixed inset-0 bg-bg/80 backdrop-blur-sm z-50 flex items-center justify-center">
      <div className="w-full max-w-2xl bg-surface-1 border border-border shadow-xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <h2 className="text-lg font-semibold text-text-primary">Notification Settings</h2>
            <p className="text-xs text-text-secondary">Configure alert delivery channels and thresholds</p>
          </div>
          <button
            onClick={() => setIsOpen(false)}
            className="p-2 hover:bg-surface-2 rounded transition-colors"
          >
            <X className="w-4 h-4 text-text-tertiary" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Channel Toggles */}
          <section>
            <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-4">
              Notification Channels
            </h3>
            <div className="grid grid-cols-3 gap-4">
              {/* Email */}
              <div
                className={cn(
                  'p-4 border rounded cursor-pointer transition-colors',
                  config.email_enabled
                    ? 'border-bloomberg bg-bloomberg/5'
                    : 'border-border-subtle bg-surface-2'
                )}
                onClick={() => setConfig((p) => ({ ...p, email_enabled: !p.email_enabled }))}
              >
                <div className="flex items-center justify-between mb-2">
                  <Mail className="w-5 h-5 text-text-secondary" />
                  <div
                    className={cn(
                      'w-4 h-4 rounded-full border-2',
                      config.email_enabled
                        ? 'border-bloomberg bg-bloomberg'
                        : 'border-text-tertiary'
                    )}
                  >
                    {config.email_enabled && <Check className="w-3 h-3 text-bg" />}
                  </div>
                </div>
                <div className="text-sm font-medium text-text-primary">Email</div>
                <div className="text-2xs text-text-tertiary mt-1">CRITICAL alerts only</div>
              </div>

              {/* Slack */}
              <div
                className={cn(
                  'p-4 border rounded cursor-pointer transition-colors',
                  config.slack_enabled
                    ? 'border-bloomberg bg-bloomberg/5'
                    : 'border-border-subtle bg-surface-2'
                )}
                onClick={() => setConfig((p) => ({ ...p, slack_enabled: !p.slack_enabled }))}
              >
                <div className="flex items-center justify-between mb-2">
                  <MessageSquare className="w-5 h-5 text-text-secondary" />
                  <div
                    className={cn(
                      'w-4 h-4 rounded-full border-2',
                      config.slack_enabled
                        ? 'border-bloomberg bg-bloomberg'
                        : 'border-text-tertiary'
                    )}
                  >
                    {config.slack_enabled && <Check className="w-3 h-3 text-bg" />}
                  </div>
                </div>
                <div className="text-sm font-medium text-text-primary">Slack</div>
                <div className="text-2xs text-text-tertiary mt-1">CRITICAL + WARNING</div>
              </div>

              {/* Browser */}
              <div
                className={cn(
                  'p-4 border rounded cursor-pointer transition-colors',
                  config.browser_enabled
                    ? 'border-bloomberg bg-bloomberg/5'
                    : 'border-border-subtle bg-surface-2'
                )}
                onClick={requestBrowserPermission}
              >
                <div className="flex items-center justify-between mb-2">
                  <Smartphone className="w-5 h-5 text-text-secondary" />
                  <div
                    className={cn(
                      'w-4 h-4 rounded-full border-2',
                      config.browser_enabled
                        ? 'border-bloomberg bg-bloomberg'
                        : 'border-text-tertiary'
                    )}
                  >
                    {config.browser_enabled && <Check className="w-3 h-3 text-bg" />}
                  </div>
                </div>
                <div className="text-sm font-medium text-text-primary">Browser</div>
                <div className="text-2xs text-text-tertiary mt-1">All severities</div>
              </div>
            </div>
          </section>

          {/* Alert Thresholds */}
          <section>
            <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-4">
              Alert Thresholds
            </h3>
            <div className="space-y-3">
              {[
                { key: 'recession_risk', label: 'Recession Risk', unit: '%', max: 100 },
                { key: 'vix', label: 'VIX Spike', unit: '', max: 100 },
                { key: 'anomaly_score', label: 'Anomaly Score', unit: '', max: 1, step: 0.05 },
                { key: 'hy_spreads', label: 'HY Spreads', unit: 'bps', max: 1000 },
                { key: 'geo_risk', label: 'Geo Risk', unit: 'σ', max: 3, step: 0.1 },
                { key: 'options_fear', label: 'Options Fear', unit: '', max: 100 },
                { key: 'options_greed', label: 'Options Greed', unit: '', max: 100 },
              ].map((threshold) => (
                <div key={threshold.key} className="flex items-center justify-between py-2">
                  <span className="text-sm text-text-primary">{threshold.label}</span>
                  <div className="flex items-center gap-3">
                    <input
                      type="number"
                      value={config.thresholds[threshold.key as keyof typeof config.thresholds]}
                      onChange={(e) =>
                        updateThreshold(
                          threshold.key as keyof NotificationConfig['thresholds'],
                          parseFloat(e.target.value)
                        )
                      }
                      step={threshold.step || 1}
                      max={threshold.max}
                      min={0}
                      className="w-20 px-2 py-1 bg-bg border border-border rounded text-right text-sm"
                    />
                    <span className="text-xs text-text-tertiary w-8">{threshold.unit}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Quiet Hours */}
          <section>
            <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-4">
              Quiet Hours
            </h3>
            <div className="p-4 bg-surface-2 border border-border-subtle rounded">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-text-secondary" />
                  <span className="text-sm text-text-primary">Suppress non-critical alerts</span>
                </div>
                <button
                  onClick={() =>
                    setConfig((p) => ({
                      ...p,
                      quiet_hours: { ...p.quiet_hours, enabled: !p.quiet_hours.enabled },
                    }))
                  }
                  className={cn(
                    'w-10 h-5 rounded-full transition-colors relative',
                    config.quiet_hours.enabled ? 'bg-bloomberg' : 'bg-surface-3'
                  )}
                >
                  <div
                    className={cn(
                      'absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform',
                      config.quiet_hours.enabled ? 'right-0.5' : 'left-0.5'
                    )}
                  />
                </button>
              </div>

              {config.quiet_hours.enabled && (
                <div className="flex items-center gap-4">
                  <div className="flex-1">
                    <label className="text-xs text-text-tertiary">Start</label>
                    <input
                      type="number"
                      value={config.quiet_hours.start}
                      onChange={(e) =>
                        setConfig((p) => ({
                          ...p,
                          quiet_hours: { ...p.quiet_hours, start: parseInt(e.target.value) },
                        }))
                      }
                      min={0}
                      max={23}
                      className="w-full px-2 py-1 bg-bg border border-border rounded text-sm"
                    />
                  </div>
                  <span className="text-text-tertiary pt-4">to</span>
                  <div className="flex-1">
                    <label className="text-xs text-text-tertiary">End</label>
                    <input
                      type="number"
                      value={config.quiet_hours.end}
                      onChange={(e) =>
                        setConfig((p) => ({
                          ...p,
                          quiet_hours: { ...p.quiet_hours, end: parseInt(e.target.value) },
                        }))
                      }
                      min={0}
                      max={23}
                      className="w-full px-2 py-1 bg-bg border border-border rounded text-sm"
                    />
                  </div>
                </div>
              )}
            </div>
          </section>

          {/* Test Results */}
          {testResults && (
            <section className="p-4 bg-surface-2 border border-border-subtle rounded">
              <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
                Test Results
              </h3>
              <div className="flex gap-4">
                {Object.entries(testResults).map(([channel, success]) => (
                  <div key={channel} className="flex items-center gap-2">
                    <div
                      className={cn(
                        'w-2 h-2 rounded-full',
                        success ? 'bg-green' : 'bg-red'
                      )}
                    />
                    <span className="text-sm capitalize">{channel}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between pt-4 border-t border-border">
            <button
              onClick={testChannels}
              disabled={isLoading}
              className="px-4 py-2 border border-border-subtle rounded text-sm font-medium text-text-secondary hover:bg-surface-2 transition-colors disabled:opacity-50"
            >
              {isLoading ? 'Testing...' : 'Test All Channels'}
            </button>

            <div className="flex items-center gap-3">
              {isSaved && (
                <span className="text-sm text-green flex items-center gap-1">
                  <Check className="w-4 h-4" />
                  Saved
                </span>
              )}
              <button
                onClick={saveConfig}
                disabled={isLoading}
                className="px-6 py-2 bg-bloomberg text-bg rounded text-sm font-medium hover:bg-bloomberg/90 transition-colors disabled:opacity-50"
              >
                {isLoading ? 'Saving...' : 'Save Settings'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
