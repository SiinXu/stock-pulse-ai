import { describe, expect, it } from 'vitest';
import { APPLICATION_NAVIGATION_ITEMS } from '../navigation';

describe('application navigation descriptor', () => {
  it('retains the approved flat canonical route order', () => {
    expect(APPLICATION_NAVIGATION_ITEMS.map(({ key, to }) => [key, to])).toEqual([
      ['home', '/'],
      ['chat', '/chat'],
      ['screening', '/screening'],
      ['portfolio', '/portfolio'],
      ['decision-signals', '/decision-signals'],
      ['backtest', '/backtest'],
      ['alerts', '/alerts'],
      ['usage', '/usage'],
      ['settings', '/settings'],
    ]);
  });

  it('has unique keys and targets without unapproved Research or More entries', () => {
    const keys = APPLICATION_NAVIGATION_ITEMS.map(({ key }) => key);
    const targets = APPLICATION_NAVIGATION_ITEMS.map(({ to }) => to);

    expect(new Set(keys).size).toBe(keys.length);
    expect(new Set(targets).size).toBe(targets.length);
    expect(keys).not.toContain('research');
    expect(keys).not.toContain('more');
    expect(targets).not.toContain('/research');
    expect(targets).not.toContain('/more');
  });
});
