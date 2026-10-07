// Panels must show "—" / "n/a" for missing data, never a made-up value. These patterns turned
// "unknown" into a real-looking number (0.0%, Sharpe 0.00, risk appetite 50 = "neutral").
import { readFileSync, readdirSync, statSync } from 'fs';
import { join } from 'path';
import { describe, expect, it } from 'vitest';

const ROOT = join(__dirname, '..', 'components', 'sections');
const PATTERNS: [RegExp, string][] = [
  [/\?\?\s*50\b/, '?? 50 (fabricated neutral midpoint)'],
  [/\|\|\s*0\)\.toFixed/, '(x || 0).toFixed — prints 0 for missing'],
  [/\|\|\s*0\)\s*\*\s*100\)\.toFixed/, '((x || 0) * 100).toFixed — prints 0% for missing'],
  [/\?\?\s*0\.5,\s*$/m, '?? 0.5 default for a rate'],
];

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : p.endsWith('.tsx') ? [p] : [];
  });
}

describe('panels never fabricate values for missing data', () => {
  it('has no display fallbacks that invent numbers', () => {
    const hits: string[] = [];
    for (const f of files(ROOT)) {
      const lines = readFileSync(f, 'utf8').split('\n');
      lines.forEach((line, i) => {
        if (line.trim().startsWith('//')) return;
        for (const [re, why] of PATTERNS) if (re.test(line)) hits.push(`${f.replace(ROOT, 'sections')}:${i + 1} ${why}`);
      });
    }
    expect(hits).toEqual([]);
  });
});
