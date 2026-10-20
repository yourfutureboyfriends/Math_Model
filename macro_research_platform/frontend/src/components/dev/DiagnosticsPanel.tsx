/**
 * Developer diagnostics panel for runtime monitoring
 * Shows backend health, API status, data freshness
 */

import { useState, useEffect } from 'react';
import { useMacroStore } from '@/store/macroStore';
import { api } from '@/lib/apiClient';

interface HealthStatus {
  status: string;
  timestamp?: string;
}

export function DiagnosticsPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(false);

  const meta = useMacroStore((s) => s.meta);
  const regime = useMacroStore((s) => s.regime);
  const signals = useMacroStore((s) => s.signals);

  useEffect(() => {
    if (isOpen) {
      setLoading(true);
      api.health()
        .then(setHealth)
        .catch(() => setHealth({ status: 'error' }))
        .finally(() => setLoading(false));
    }
  }, [isOpen]);

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-4 right-4 bg-gray-800 text-white px-3 py-2 rounded text-xs font-mono shadow-lg hover:bg-gray-700 transition-colors z-50"
      >
        🔧 Diagnostics
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 bg-gray-900 text-white p-4 rounded shadow-lg max-w-md z-50 border border-gray-700">
      <div className="flex justify-between items-center mb-3">
        <h3 className="font-bold text-sm">System Diagnostics</h3>
        <button
          onClick={() => setIsOpen(false)}
          className="text-gray-400 hover:text-white text-lg"
        >
          ✕
        </button>
      </div>

      <div className="space-y-2 text-xs font-mono">
        <div className="flex justify-between">
          <span className="text-gray-400">Backend Status:</span>
          <span className={meta.dataStatus !== 'error' ? 'text-green-400' : 'text-red-400'}>
            {meta.dataStatus !== 'error' ? '✓ Connected' : '✗ Offline'}
          </span>
        </div>

        <div className="flex justify-between">
          <span className="text-gray-400">Health Check:</span>
          {loading ? (
            <span className="text-yellow-400">Loading...</span>
          ) : (
            <span className={health?.status === 'ok' ? 'text-green-400' : 'text-yellow-400'}>
              {health?.status || 'unknown'}
            </span>
          )}
        </div>

        <div className="flex justify-between">
          <span className="text-gray-400">Data Status:</span>
          <span className="text-blue-400">{meta.dataStatus}</span>
        </div>

        <div className="flex justify-between">
          <span className="text-gray-400">Last Refreshed:</span>
          <span className="text-gray-300">
            {meta.lastUpdated
              ? new Date(meta.lastUpdated).toLocaleTimeString()
              : 'N/A'}
          </span>
        </div>

        {regime.current && (
          <div className="pt-2 border-t border-gray-700 mt-2">
            <div className="text-gray-400 mb-1">Regime:</div>
            <div className="text-green-400">{regime.current}</div>
            <div className="text-gray-500">Confidence: {regime.confidence?.toFixed(2)}</div>
          </div>
        )}

        {signals.growth.score !== null && (
          <div className="pt-2 border-t border-gray-700 mt-2">
            <div className="text-gray-400 mb-1">Signals:</div>
            <div className="grid grid-cols-4 gap-2 text-center">
              <div>
                <div className="text-gray-500">Growth</div>
                <div className="text-green-400">{signals.growth.score.toFixed(2)}</div>
              </div>
              <div>
                <div className="text-gray-500">Inflation</div>
                <div className="text-yellow-400">{signals.inflation.score?.toFixed(2) ?? '-'}</div>
              </div>
              <div>
                <div className="text-gray-500">Liquidity</div>
                <div className="text-blue-400">{signals.liquidity.score?.toFixed(2) ?? '-'}</div>
              </div>
              <div>
                <div className="text-gray-500">Risk</div>
                <div className="text-red-400">{signals.risk.score?.toFixed(2) ?? '-'}</div>
              </div>
            </div>
          </div>
        )}

        <div className="pt-2 border-t border-gray-700 mt-2">
          <button
            onClick={() => window.location.reload()}
            className="w-full bg-blue-600 hover:bg-blue-700 px-3 py-1.5 rounded text-xs transition-colors"
          >
            Refresh Page
          </button>
        </div>
      </div>
    </div>
  );
}
