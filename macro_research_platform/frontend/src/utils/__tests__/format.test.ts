// Format Library Unit Tests
// Each expectation follows the contract documented on the formatter in ../format.ts
// (inputs in the units the API actually sends: rates in percent, changes as fractions,
// durations in months; missing values render as an em dash).

import { describe, it, expect } from 'vitest';
import {
  fmtPrice,
  fmtPriceInt,
  fmtMagnitude,
  fmtRate,
  fmtRateChange,
  fmtChange,
  fmtFx,
  fmtVol,
  fmtSignal,
  fmtProbability,
  fmtDuration,
  fmtPct,
} from '../format';

const DASH = '—';

describe('format library', () => {
  describe('fmtPrice', () => {
    it('formats with thousands separators and 2 decimals', () => {
      expect(fmtPrice(4200.5)).toBe('4,200.50');
    });

    it('formats zero', () => {
      expect(fmtPrice(0)).toBe('0.00');
    });

    it('respects custom decimals', () => {
      expect(fmtPrice(123.456, 0)).toBe('123');
      expect(fmtPrice(123.456, 4)).toBe('123.4560');
    });

    it('formats null / undefined / NaN as a dash', () => {
      expect(fmtPrice(null)).toBe(DASH);
      expect(fmtPrice(undefined as unknown as null)).toBe(DASH);
      expect(fmtPrice(NaN)).toBe(DASH);
    });
  });

  describe('fmtPriceInt', () => {
    it('rounds and adds thousands separators (index levels)', () => {
      expect(fmtPriceInt(4200.5)).toBe('4,201');
      expect(fmtPriceInt(7635.08)).toBe('7,635');
      expect(fmtPriceInt(999)).toBe('999');
    });

    it('formats null as a dash', () => {
      expect(fmtPriceInt(null)).toBe(DASH);
    });
  });

  describe('fmtMagnitude', () => {
    it('uses K / M / B suffixes', () => {
      expect(fmtMagnitude(1500)).toBe('1.5K');
      expect(fmtMagnitude(1500000)).toBe('1.5M');
      expect(fmtMagnitude(1500000000)).toBe('1.5B');
      expect(fmtMagnitude(-2500000)).toBe('-2.5M');
    });
  });

  describe('fmtRate', () => {
    it('formats a rate already in percent', () => {
      expect(fmtRate(4.5)).toBe('4.50%');
      expect(fmtRate(3.64)).toBe('3.64%');
    });

    it('handles negative rates', () => {
      expect(fmtRate(-0.5)).toBe('-0.50%');
    });

    it('formats null as a dash', () => {
      expect(fmtRate(null)).toBe(DASH);
    });
  });

  describe('fmtRateChange', () => {
    it('signs non-zero changes and leaves zero unsigned', () => {
      expect(fmtRateChange(0.25)).toBe('+0.25%');
      expect(fmtRateChange(-0.1)).toBe('-0.10%');
      expect(fmtRateChange(0)).toBe('0.00%');
    });
  });

  describe('fmtChange', () => {
    it('adds + prefix for positive fractional changes', () => {
      expect(fmtChange(0.025)).toBe('+2.50%');
    });

    it('adds - prefix for negative changes', () => {
      expect(fmtChange(-0.015)).toBe('-1.50%');
    });

    it('formats zero (and values rounding to zero) without a sign', () => {
      expect(fmtChange(0)).toBe('0.00%');
      expect(fmtChange(-0.00001)).toBe('0.00%');
    });

    it('formats null as a dash', () => {
      expect(fmtChange(null)).toBe(DASH);
    });
  });

  describe('fmtFx', () => {
    it('formats FX pairs with 4 decimals', () => {
      expect(fmtFx(1.12345)).toBe('1.1235');
    });

    it('respects custom decimals', () => {
      expect(fmtFx(1.12345, 2)).toBe('1.12');
    });

    it('formats null as a dash', () => {
      expect(fmtFx(null)).toBe(DASH);
    });
  });

  describe('fmtVol', () => {
    it('formats volatility with 1 decimal', () => {
      expect(fmtVol(15.5)).toBe('15.5');
    });

    it('formats null as a dash', () => {
      expect(fmtVol(null)).toBe(DASH);
    });
  });

  describe('fmtSignal', () => {
    it('formats positive signals with +', () => {
      expect(fmtSignal(0.65)).toBe('+0.65');
    });

    it('formats negative signals', () => {
      expect(fmtSignal(-0.32)).toBe('-0.32');
    });

    it('formats zero without a sign', () => {
      expect(fmtSignal(0)).toBe('0.00');
    });

    it('formats null as a dash', () => {
      expect(fmtSignal(null)).toBe(DASH);
    });
  });

  describe('fmtProbability', () => {
    it('formats as percentage', () => {
      expect(fmtProbability(0.75)).toBe('75%');
    });

    it('handles zero and clamps to [0, 1]', () => {
      expect(fmtProbability(0)).toBe('0%');
      expect(fmtProbability(1.4)).toBe('100%');
    });

    it('formats null as a dash', () => {
      expect(fmtProbability(null)).toBe(DASH);
    });
  });

  describe('fmtPct', () => {
    it('does not clamp exposures above 100% or below 0', () => {
      expect(fmtPct(1.5)).toBe('150.0%');
      expect(fmtPct(-0.12)).toBe('-12.0%');
    });

    it('signs when asked, never "+0.0%" or "-0.0%"', () => {
      expect(fmtPct(0.0123, 2, true)).toBe('+1.23%');
      expect(fmtPct(-0.0000001, 1, true)).toBe('0.0%');
    });
  });

  describe('fmtDuration', () => {
    it('formats months with correct pluralisation', () => {
      expect(fmtDuration(6)).toBe('6 months');
      expect(fmtDuration(1)).toBe('1 month');
    });

    it('formats null as a dash', () => {
      expect(fmtDuration(null)).toBe(DASH);
    });
  });
});
