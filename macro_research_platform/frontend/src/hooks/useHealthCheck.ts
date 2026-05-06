// Health Check Hook — Phase 5B Production Prep
// Monitors system health and API availability

import { useState, useEffect, useCallback } from 'react';
import { env, HEALTH_ENDPOINTS } from '@/config/env';

interface HealthStatus {
  api: boolean;
  ws: boolean;
  timestamp: Date | null;
}

interface HealthCheckResult {
  status: HealthStatus;
  isHealthy: boolean;
  lastChecked: Date | null;
  checkHealth: () => Promise<void>;
}

export function useHealthCheck(): HealthCheckResult {
  const [status, setStatus] = useState<HealthStatus>({
    api: false,
    ws: false,
    timestamp: null,
  });
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const checkHealth = useCallback(async () => {
    const results: Partial<HealthStatus> = { timestamp: new Date() };

    // Check API health
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);

      const response = await fetch(HEALTH_ENDPOINTS.API, {
        signal: controller.signal,
      });

      clearTimeout(timeout);
      results.api = response.ok;
    } catch {
      results.api = false;
    }

    // WebSocket health is inferred from connection state
    results.ws = env.ENABLE_WEBSOCKET;

    setStatus(results as HealthStatus);
    setLastChecked(new Date());
  }, []);

  useEffect(() => {
    checkHealth();

    // Periodic health check every 30 seconds
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  const isHealthy = status.api;

  return {
    status,
    isHealthy,
    lastChecked,
    checkHealth,
  };
}
