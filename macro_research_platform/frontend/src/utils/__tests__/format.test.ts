// Format Library Unit Tests — Phase 4D
// Tests for all format utility functions

import { describe, it, expect } from 'vitest';
import {
  fmtPrice,
  fmtPriceInt,
  fmtRate,
  fmtChange,
  fmtFx,
  fmtVol,
  fmtSignal,
  fmtProbability,
  fmtDuration,
} from '../format';

describe('format library', () => {
  describe('fmtPrice', () => {
    it('formats positive prices with 2 decimals', () => {
      expect(fmtPrice(123.456)).toBe('$123.46');
    });

    it('formats null as --', () => {
      expect(fmtPrice(null)).toBe('--');
    });

    it('formats undefined as --', () => {
      expect(fmtPrice(undefined)).toBe('--');
    });

    it('formats zero', () => {
      expect(fmtPrice(0)).toBe('$0.00');
    });

    it('respects custom decimals', () => {
      expect(fmtPrice(123.456, 0)).toBe('$123');
      expect(fmtPrice(123.456, 4)).toBe('$123.4560');
    });
  });

  describe('fmtPriceInt', () => {
    it('formats with K suffix for thousands', () => {
      expect(fmtPriceInt(1500)).toBe('1.5K');
    });

    it('formats with M suffix for millions', () => {
      expect(fmtPriceInt(1500000)).toBe('1.5M');
    });

    it('formats with B suffix for billions', () => {
      expect(fmtPriceInt(1500000000)).toBe('1.5B');
    });

    it('formats small numbers without suffix', () => {
      expect(fmtPriceInt(999)).toBe('999');
    });

    it('formats null as --', () => {
      expect(fmtPriceInt(null)).toBe('--');
    });
  });

  describe('fmtRate', () => {
    it('formats rate as percentage', () => {
      expect(fmtRate(0.045)).toBe('4.50%');
    });

    it('handles negative rates', () => {
      expect(fmtRate(-0.012)).toBe('-1.20%');
    });

    it('formats null as --', () => {
      expect(fmtRate(null)).toBe('--');
    });
  });

  describe('fmtChange', () => {
    it('adds + prefix for positive changes', () => {
      expect(fmtChange(0.025)).toBe('+2.50%');
    });

    it('adds - prefix for negative changes', () => {
      expect(fmtChange(-0.015)).toBe('-1.50%');
    });

    it('formats zero change', () => {
      expect(fmtChange(0)).toBe('0.00%');
    });

    it('formats null as --', () => {
      expect(fmtChange(null)).toBe('--');
    });
  });

  describe('fmtFx', () => {
    it('formats FX pairs with 4 decimals', () => {
      expect(fmtFx(1.12345)).toBe('1.1235');
    });

    it('respects custom decimals', () => {
      expect(fmtFx(1.12345, 2)).toBe('1.12');
    });

    it('formats null as --', () => {
      expect(fmtFx(null)).toBe('--');
    });
  });

  describe('fmtVol', () => {
    it('formats volatility with % suffix', () => {
      expect(fmtVol(15.5)).toBe('15.5');
    });

    it('formats null as --', () => {
      expect(fmtVol(null)).toBe('--');
    });
  });

  describe('fmtSignal', () => {
    it('formats positive signals with +', () => {
      expect(fmtSignal(0.65)).toBe('+0.65');
    });

    it('formats negative signals', () => {
      expect(fmtSignal(-0.32)).toBe('-0.32');
    });

    it('formats zero', () => {
      expect(fmtSignal(0)).toBe('0.00');
    });

    it('formats null as --', () => {
      expect(fmtSignal(null)).toBe('--');
    });
  });

  describe('fmtProbability', () => {
    it('formats as percentage', () => {
      expect(fmtProbability(0.75)).toBe('75%');
    });

    it('handles zero', () => {
      expect(fmtProbability(0)).toBe('0%');
    });

    it('formats null as --', () => {
      expect(fmtProbability(null)).toBe('--');
    });
  });

  describe('fmtDuration', () => {
    it('formats days', () => {
      expect(fmtDuration(5)).toBe('5d');
    });

    it('formats weeks', () => {
      expect(fmtDuration(21)).toBe('3w');
    });

    it('formats months', () => {
      expect(fmtDuration(90)).toBe('3mo');
    });

    it('formats years', () => {
      expect(fmtDuration(730)).toBe('2y');
    });

    it('formats null as --', () => {
      expect(fmtDuration(null)).toBe('--');
    });
  });
});
