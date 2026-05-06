// Macro Store Unit Tests — Phase 4D
// Tests for Zustand store actions and selectors

import { describe, it, expect, beforeEach } from 'vitest';
import { useMacroStore } from '../macroStore';

// Reset store before each test
beforeEach(() => {
  useMacroStore.setState({
    prices: {
      SPX: null,
      NDX: null,
      VIX: null,
      TENYR: null,
      TWYR: null,
      FED: null,
      DXY: null,
      EURUSD: null,
      GBPUSD: null,
      USDJPY: null,
      USDCAD: null,
      USDCHF: null,
      AUDUSD: null,
      NZDUSD: null,
      GLD: null,
      WTI: null,
    },
    changes: {},
    regime: {
      current: null,
      confidence: null,
      duration: null,
      probabilities: {
        goldilocks: null,
        reflation: null,
        stagflation: null,
        slowdown: null,
      },
    },
    signals: {
      growth: { score: null, threeMonth: null, state: null },
      inflation: { score: null, threeMonth: null, state: null },
      liquidity: { score: null, threeMonth: null, state: null },
      risk: { score: null, threeMonth: null, state: null },
    },
    ensemble: {
      score: null,
      conviction: null,
      agreement: null,
      riskBudget: null,
    },
    meta: {
      latestDate: null,
      dataStatus: 'loading',
      lastUpdated: null,
    },
    wsConnected: false,
    wsError: null,
  });
});

describe('macroStore', () => {
  describe('getters', () => {
    it('getPrice returns price for symbol', () => {
      useMacroStore.setState({
        prices: { ...useMacroStore.getState().prices, SPX: 4500.5 },
      });
      const price = useMacroStore.getState().getPrice('SPX');
      expect(price).toBe(4500.5);
    });

    it('getPrice returns null for unset price', () => {
      const price = useMacroStore.getState().getPrice('SPX');
      expect(price).toBeNull();
    });

    it('getChange returns change for symbol', () => {
      useMacroStore.setState({
        changes: { SPX: 0.025 },
      });
      const change = useMacroStore.getState().getChange('SPX');
      expect(change).toBe(0.025);
    });

    it('getChange returns null for unset change', () => {
      const change = useMacroStore.getState().getChange('SPX');
      expect(change).toBeNull();
    });
  });

  describe('state updates', () => {
    it('updates prices correctly', () => {
      useMacroStore.setState({
        prices: { ...useMacroStore.getState().prices, SPX: 4500 },
      });
      expect(useMacroStore.getState().prices.SPX).toBe(4500);
    });

    it('updates regime correctly', () => {
      useMacroStore.setState({
        regime: {
          ...useMacroStore.getState().regime,
          current: 'goldilocks',
          confidence: 0.75,
        },
      });
      expect(useMacroStore.getState().regime.current).toBe('goldilocks');
      expect(useMacroStore.getState().regime.confidence).toBe(0.75);
    });

    it('updates signals correctly', () => {
      useMacroStore.setState({
        signals: {
          ...useMacroStore.getState().signals,
          growth: { score: 0.65, threeMonth: 0.45, state: 'accelerating' },
        },
      });
      expect(useMacroStore.getState().signals.growth.score).toBe(0.65);
    });

    it('updates ensemble correctly', () => {
      useMacroStore.setState({
        ensemble: {
          ...useMacroStore.getState().ensemble,
          score: 0.8,
          conviction: 'HIGH',
        },
      });
      expect(useMacroStore.getState().ensemble.score).toBe(0.8);
      expect(useMacroStore.getState().ensemble.conviction).toBe('HIGH');
    });
  });

  describe('meta state', () => {
    it('tracks loading status', () => {
      useMacroStore.setState({
        meta: { ...useMacroStore.getState().meta, dataStatus: 'loading' },
      });
      expect(useMacroStore.getState().meta.dataStatus).toBe('loading');
    });

    it('tracks live status', () => {
      useMacroStore.setState({
        meta: { ...useMacroStore.getState().meta, dataStatus: 'live' },
      });
      expect(useMacroStore.getState().meta.dataStatus).toBe('live');
    });

    it('tracks error status', () => {
      useMacroStore.setState({
        meta: { ...useMacroStore.getState().meta, dataStatus: 'error' },
      });
      expect(useMacroStore.getState().meta.dataStatus).toBe('error');
    });
  });

  describe('WebSocket state', () => {
    it('tracks connection status', () => {
      useMacroStore.setState({ wsConnected: true });
      expect(useMacroStore.getState().wsConnected).toBe(true);
    });

    it('tracks error messages', () => {
      useMacroStore.setState({ wsError: 'Connection failed' });
      expect(useMacroStore.getState().wsError).toBe('Connection failed');
    });
  });
});
