import { describe, expect, it } from 'vitest';
import { FUNCTIONS, findFunction } from './functions';

describe('market destinations', () => {
 it('gives every canonical code and shortcut exactly one destination', () => {
  const owners = new Map<string, string>();
  for (const page of FUNCTIONS) for (const code of [page.code, ...(page.aliases ?? [])]) {
   expect(owners.has(code), `${code} is shared with ${owners.get(code)}`).toBe(false);
   owners.set(code, page.code);
   expect(findFunction(code)?.code).toBe(page.code);
  }
 });
 it('preserves existing ambiguous shortcut destinations and distinct tools', () => {
  for (const [token, code] of Object.entries({ CHART:'CHART', ALPHA:'ALPHA', CREDIT:'CRPR', TOP:'WEI', GRID:'LP', NEWS:'N', BDP:'DATA', OAS:'CRED', SIG:'EDGE' })) expect(findFunction(token)?.code).toBe(code);
  expect(findFunction('__proto__')).toBeUndefined();
 });
});
