import { describe, expect, it } from 'vitest';
import { compactMoney } from './StatusBar';

describe('account bar figures', () => {
  it('abbreviates and signs money', () => {
    expect(compactMoney(100000)).toBe('100.0K');
    expect(compactMoney(2_345_678)).toBe('2.35M');
    expect(compactMoney(-1500, true)).toBe('−1500');
    expect(compactMoney(1500, true)).toBe('+1500');
    expect(compactMoney(null)).toBe('—');
  });
});
