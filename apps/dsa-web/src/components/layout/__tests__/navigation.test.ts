import { describe, expect, it } from 'vitest';
import { APP_ROUTE_PATHS, LEGACY_ROUTE_PATHS } from '../../../routing/routes';
import {
  APPLICATION_NAVIGATION_ITEMS,
  shouldDelegateCurrentDocumentNavigation,
} from '../navigation';

describe('application navigation descriptor', () => {
  it('converges to five primary domains with approved secondary routes', () => {
    expect(APPLICATION_NAVIGATION_ITEMS.map(({ key, to }) => [key, to])).toEqual([
      ['home', APP_ROUTE_PATHS.home],
      ['research', APP_ROUTE_PATHS.researchMarket],
      ['portfolio', APP_ROUTE_PATHS.portfolio],
      ['agent', APP_ROUTE_PATHS.agent],
      ['settings', APP_ROUTE_PATHS.settings],
    ]);
    expect(APPLICATION_NAVIGATION_ITEMS[0]?.children?.map(({ key, to }) => [key, to])).toEqual([
      ['decision-signals', APP_ROUTE_PATHS.decisionSignals],
      ['alerts', APP_ROUTE_PATHS.alerts],
    ]);
    expect(APPLICATION_NAVIGATION_ITEMS[1]?.children?.map(({ key, to }) => [key, to])).toEqual([
      ['research-market', APP_ROUTE_PATHS.researchMarket],
      ['research-discover', APP_ROUTE_PATHS.researchDiscover],
      ['research-backtest', APP_ROUTE_PATHS.researchBacktest],
    ]);
  });

  it('has unique descriptor keys and no legacy or dead utility targets', () => {
    const entries = APPLICATION_NAVIGATION_ITEMS.flatMap((item) => [item, ...(item.children ?? [])]);
    const keys = entries.map(({ key }) => key);
    const targets = entries.map(({ to }) => to);

    expect(new Set(keys).size).toBe(keys.length);
    expect(keys).not.toContain('more');
    expect(keys).not.toContain('usage');
    expect(targets).not.toContain(LEGACY_ROUTE_PATHS.usage);
    expect(targets).not.toContain(LEGACY_ROUTE_PATHS.screening);
    expect(targets).not.toContain(LEGACY_ROUTE_PATHS.backtest);
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
