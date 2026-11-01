import { describe, expect, it } from 'vitest';
import { onAccent } from './accentContrast';

describe('text on the accent colour', () => {
  it('is dark on light accents and white on dark ones', () => {
    expect(onAccent([214, 182, 136])).toEqual([10, 14, 20]);   // Moriah gold: white would be 1.9:1
    expect(onAccent([240, 112, 48])).toEqual([10, 14, 20]);    // default orange
    expect(onAccent([15, 35, 62])).toEqual([255, 255, 255]);   // BIFS navy
    expect(onAccent([8, 145, 178])).toEqual([10, 14, 20]);     // light-theme teal
  });
});
