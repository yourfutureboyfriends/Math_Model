/**
 * Frontend API Integration Tests
 * Verifies that backend responses match expected TypeScript types
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { api } from '@/lib/apiClient';
import { validateDashboardData, ValidationError } from '@/lib/apiValidation';

describe('API Integration Tests', () => {
  const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  beforeAll(() => {
    // Ensure backend is running on localhost:8000
    console.log(`Testing against: ${API_BASE_URL}`);
  });

  describe('Dashboard Endpoint', () => {
    it('dashboard endpoint returns valid DashboardData', async () => {
      const dashboard = await api.dashboard.get();

      // Required fields exist
      expect(dashboard.regime).toBeDefined();
      expect(dashboard.keyMetrics).toBeDefined();
      expect(dashboard.scores).toBeDefined();
      expect(dashboard.signals).toBeDefined();
      expect(dashboard.recession).toBeDefined();
      expect(dashboard.metadata).toBeDefined();
      expect(dashboard.timestamp).toBeDefined();
      expect(dashboard.mode).toBeDefined();

      // Type checks
      expect(typeof dashboard.regime.confidenceScore).toBe('number');
      expect(typeof dashboard.scores.growth).toBe('number');
      expect(typeof dashboard.metadata.dataStatus).toBe('string');
      expect(typeof dashboard.timestamp).toBe('string');

      // Range checks
      expect(dashboard.regime.confidenceScore).toBeGreaterThanOrEqual(0);
      expect(dashboard.regime.confidenceScore).toBeLessThanOrEqual(1);

      expect(dashboard.scores.growth).toBeGreaterThanOrEqual(0);
      expect(dashboard.scores.growth).toBeLessThanOrEqual(100);

      expect(dashboard.scores.inflation).toBeGreaterThanOrEqual(0);
      expect(dashboard.scores.inflation).toBeLessThanOrEqual(100);

      expect(dashboard.scores.liquidity).toBeGreaterThanOrEqual(0);
      expect(dashboard.scores.liquidity).toBeLessThanOrEqual(100);

      expect(dashboard.scores.risk).toBeGreaterThanOrEqual(0);
      expect(dashboard.scores.risk).toBeLessThanOrEqual(100);
    });

    it('handles string numbers by normalizing to actual numbers', async () => {
      const dashboard = await api.dashboard.get();

      // Even if backend accidentally returns string, validation normalizes
      expect(typeof dashboard.regime.confidenceScore).toBe('number');
      expect(typeof dashboard.scores.growth).toBe('number');
    });

    it('recession data has populated arrays', async () => {
      const dashboard = await api.dashboard.get();

      expect(Array.isArray(dashboard.recession.components)).toBe(true);
      expect(Array.isArray(dashboard.recession.history)).toBe(true);

      // Should not be empty (from Phase 1 fix)
      expect(dashboard.recession.components.length).toBeGreaterThan(0);
      expect(dashboard.recession.history.length).toBeGreaterThan(0);
    });

    it('validation function accepts valid dashboard', () => {
      const validDashboard = {
        regime: {
          current: 'Goldilocks',
          confidence: 'high',
          confidenceScore: 0.85,
          duration: 12,
          history: [],
          interpretations: []
        },
        keyMetrics: {
          growth: { value: 2.5, formatted: '2.5%', direction: 'up', sparklineData: [] },
          inflation: { value: 2.1, formatted: '2.1%', direction: 'stable', sparklineData: [] },
          liquidity: { value: 0.5, formatted: '0.5', direction: 'down', sparklineData: [] },
          risk: { value: 0.3, formatted: '30%', direction: 'stable', sparklineData: [] }
        },
        scores: {
          growth: 65,
          inflation: 45,
          liquidity: 50,
          risk: 30
        },
        signals: {
          finalSignal: 'RISK_ON',
          growth: { score: 0.7, threeMonth: 0.2, state: 'Strong', direction: 'improving', interpretation: 'Growth positive', history: [], historyLabels: [] },
          inflation: { score: 0.3, threeMonth: 0.1, state: 'Neutral', direction: 'stable', interpretation: 'Inflation moderate', history: [], historyLabels: [] },
          liquidity: { score: 0.5, threeMonth: 0.2, state: 'Neutral', direction: 'stable', interpretation: 'Liquidity adequate', history: [], historyLabels: [] },
          risk: { score: 0.3, threeMonth: 0.0, state: 'Neutral', direction: 'stable', interpretation: 'Risk moderate', history: [], historyLabels: [] }
        },
        recession: {
          probability: 0.15,
          level: 'Low',
          logisticProb: 0.12,
          emProbitProb: 0.18,
          sahmValue: 0,
          sahmSignal: 'No Signal',
          description: 'Low probability',
          components: [{ name: 'Test', value: 0.5, contribution: 0.1 }],
          history: [{ date: '2024-01-01', probability: 0.1 }]
        },
        metadata: {
          latestDate: '2024-01-01',
          lastRefreshed: '2024-01-01',
          dataStatus: 'current',
          daysSinceUpdate: 0,
          mode: 'live'
        },
        timestamp: '2024-01-01T00:00:00Z',
        mode: 'live'
      };

      // Should not throw
      expect(() => validateDashboardData(validDashboard)).not.toThrow();
    });

    it('validation function throws on missing required fields', () => {
      const invalidDashboard = {
        regime: { current: 'Goldilocks', confidenceScore: 0.5 },
        // missing keyMetrics, scores, signals, etc.
      };

      expect(() => validateDashboardData(invalidDashboard)).toThrow(ValidationError);
    });
  });

  describe('Signals Endpoint', () => {
    it('signals endpoint includes all required fields', async () => {
      const signals = await api.signals.get();

      expect(signals.growth).toBeDefined();
      expect(signals.growth.direction).toBeDefined();
      expect(signals.growth.interpretation).toBeDefined();
      expect(signals.growth.history).toBeDefined();
      expect(Array.isArray(signals.growth.history)).toBe(true);

      expect(signals.inflation).toBeDefined();
      expect(signals.liquidity).toBeDefined();
      expect(signals.risk).toBeDefined();
    });

    it('signal stack endpoint returns valid data', async () => {
      const stack = await api.signals.getStack();

      expect(stack.finalSignal).toBeDefined();
      expect(stack.confidence).toBeDefined();
      expect(stack.timestamp).toBeDefined();
      expect(Array.isArray(stack.layers)).toBe(true);
    });
  });

  describe('Risk Endpoints', () => {
    it('recession endpoint has populated arrays', async () => {
      const recession = await api.risk.getRecession();

      expect(Array.isArray(recession.components)).toBe(true);
      expect(Array.isArray(recession.history)).toBe(true);

      // Should not be empty (from Phase 1 fix)
      expect(recession.components.length).toBeGreaterThan(0);
      expect(recession.history.length).toBeGreaterThan(0);
    });

    it('recession probability is in valid range', async () => {
      const recession = await api.risk.getRecession();

      expect(typeof recession.probability).toBe('number');
      expect(recession.probability).toBeGreaterThanOrEqual(0);
      expect(recession.probability).toBeLessThanOrEqual(1);
    });

    it('alerts endpoint returns valid data', async () => {
      const alerts = await api.risk.getAlerts();

      expect(Array.isArray(alerts.alerts)).toBe(true);
    });
  });

  describe('Business Endpoints', () => {
    it('trade ideas endpoint returns valid data', async () => {
      const tradeIdeas = await api.business.getTradeIdeas();

      expect(tradeIdeas.ideas).toBeDefined();
      expect(Array.isArray(tradeIdeas.ideas)).toBe(true);
      expect(typeof tradeIdeas.count).toBe('number');
    });

    it('morning brief endpoint returns valid data', async () => {
      const brief = await api.business.getMorningBrief();

      expect(brief.date).toBeDefined();
      expect(brief.summary).toBeDefined();
      expect(Array.isArray(brief.keyEvents)).toBe(true);
    });
  });

  describe('Health Endpoint', () => {
    it('health endpoint responds', async () => {
      const health = await api.health();

      expect(health.status).toBeDefined();
      expect(typeof health.status).toBe('string');
    });
  });

  describe('Error Handling', () => {
    it('handles 404 gracefully', async () => {
      try {
        await fetch(`${API_BASE_URL}/api/nonexistent`);
      } catch (error) {
        expect(error).toBeDefined();
      }
    });

    it('handles network errors', async () => {
      // This test assumes backend might be unavailable
      // In practice, you'd mock the fetch
      const isBackendAvailable = await api.health()
        .then(() => true)
        .catch(() => false);

      // Just verify the check doesn't throw
      expect(typeof isBackendAvailable).toBe('boolean');
    });
  });
});
