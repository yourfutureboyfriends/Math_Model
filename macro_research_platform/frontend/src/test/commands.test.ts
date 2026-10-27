import { describe, expect, it } from 'vitest';
import { resolveCommands } from '@/lib/commands';

const top = (q: string, funds = [{ id: 'main', name: 'Moriah Capital Partners' }, { id: 'bifs', name: 'BIFS' }]) => resolveCommands(q, funds)[0];

describe('<GO> command resolver', () => {
  it('opens each economy\'s macro model', () => {
    expect(top('ea model')?.key).toBe('model:ea');
    expect(top('EURO')?.key).toBe('model:ea');
    expect(top('rest of world')?.key).toBe('model:row');
    expect(top('US MODEL')?.key).toBe('model:us');
  });

  it('finds Research panels by name, initials or words', () => {
    expect(top('fund overview')?.key).toBe('panel:fund-cockpit');
    expect(top('economic calendar')?.key).toBe('panel:economic-calendar');
    expect(resolveCommands('var').some((c) => c.key === 'panel:var-stress')).toBe(true);
  });

  it('switches fund by name or id', () => {
    expect(top('bifs')?.key).toBe('fund:bifs');
    expect(top('moriah')?.key).toBe('fund:main');
  });

  it('routes functions and securities to Markets, explicit forms first', () => {
    expect(top('ECO')?.group === 'Markets' || top('ECO')?.group === 'Panel').toBe(true);
    expect(top('AAPL DES')?.key).toBe('sec:AAPL:DES');
    expect(top('SPX Index GP')?.group).toBe('Security');
    expect(top('7203.T')?.key).toBe('sec:7203.T:DES');
    expect(top('alerts')?.group).toBe('Action');
  });

  it('returns nothing for nothing', () => {
    expect(resolveCommands('   ')).toEqual([]);
  });
});
