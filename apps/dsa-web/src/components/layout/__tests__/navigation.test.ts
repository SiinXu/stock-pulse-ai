import { describe, expect, it } from 'vitest';
import { APP_ROUTE_PATHS, LEGACY_ROUTE_PATHS } from '../../../routing/routes';
import {
  APPLICATION_NAVIGATION_ITEMS,
  shouldDelegateCurrentDocumentNavigation,
} from '../navigation';

describe('application navigation descriptor', () => {
  it('retains the approved flat route order without the nested usage utility', () => {
    expect(APPLICATION_NAVIGATION_ITEMS.map(({ key, to }) => [key, to])).toEqual([
      ['home', '/'],
      ['chat', '/chat'],
      ['screening', '/screening'],
      ['portfolio', '/portfolio'],
      ['decision-signals', '/decision-signals'],
      ['backtest', '/backtest'],
      ['alerts', '/alerts'],
      ['settings', APP_ROUTE_PATHS.settings],
    ]);
  });

  it('has unique keys and targets without unapproved Research or More entries', () => {
    const keys = APPLICATION_NAVIGATION_ITEMS.map(({ key }) => key);
    const targets = APPLICATION_NAVIGATION_ITEMS.map(({ to }) => to);

    expect(new Set(keys).size).toBe(keys.length);
    expect(new Set(targets).size).toBe(targets.length);
    expect(keys).not.toContain('research');
    expect(keys).not.toContain('more');
    expect(keys).not.toContain('usage');
    expect(targets).not.toContain(LEGACY_ROUTE_PATHS.usage);
    expect(targets).not.toContain('/research');
    expect(targets).not.toContain('/more');
  });

  it('delegates only unmodified primary same-window link activation', () => {
    const currentTarget = document.createElement('a');
    const event = (overrides: Record<string, unknown> = {}) => ({
      defaultPrevented: false,
      button: 0,
      metaKey: false,
      ctrlKey: false,
      shiftKey: false,
      altKey: false,
      currentTarget,
      ...overrides,
    }) as Parameters<typeof shouldDelegateCurrentDocumentNavigation>[0];

    expect(shouldDelegateCurrentDocumentNavigation(event())).toBe(true);
    for (const modifier of ['metaKey', 'ctrlKey', 'shiftKey', 'altKey']) {
      expect(shouldDelegateCurrentDocumentNavigation(event({ [modifier]: true }))).toBe(false);
    }
    expect(shouldDelegateCurrentDocumentNavigation(event({ button: 1 }))).toBe(false);
    expect(shouldDelegateCurrentDocumentNavigation(event({ defaultPrevented: true }))).toBe(false);

    currentTarget.target = '_blank';
    expect(shouldDelegateCurrentDocumentNavigation(event())).toBe(false);
    currentTarget.target = '_self';
    currentTarget.setAttribute('download', 'report.json');
    expect(shouldDelegateCurrentDocumentNavigation(event())).toBe(false);
  });
});
