// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { APPLICATION_NAVIGATION_ITEMS } from '../../components/layout/navigation';
import { APP_ROUTE_PATHS, LEGACY_ROUTE_PATHS } from '../routes';

/**
 * Mechanical route inventory for Navigation IA (#368).
 * Keep this table aligned with App.tsx + APPLICATION_NAVIGATION_ITEMS.
 */
const CANONICAL_SHELL_ROUTES = [
  APP_ROUTE_PATHS.home,
  APP_ROUTE_PATHS.agent,
  APP_ROUTE_PATHS.portfolio,
  APP_ROUTE_PATHS.signals,
  APP_ROUTE_PATHS.approvals,
  APP_ROUTE_PATHS.stockDetails,
  APP_ROUTE_PATHS.research,
  APP_ROUTE_PATHS.researchMarket,
  APP_ROUTE_PATHS.researchDiscover,
  APP_ROUTE_PATHS.researchAnalysis,
  APP_ROUTE_PATHS.researchBacktest,
  APP_ROUTE_PATHS.calculators,
  APP_ROUTE_PATHS.researchSkillOutcomes,
  APP_ROUTE_PATHS.settings,
] as const;

const LEGACY_REDIRECT_MAP: ReadonlyArray<readonly [string, string]> = [
  [LEGACY_ROUTE_PATHS.decisionSignals, APP_ROUTE_PATHS.signals],
  [LEGACY_ROUTE_PATHS.alerts, APP_ROUTE_PATHS.signals],
  [LEGACY_ROUTE_PATHS.screening, APP_ROUTE_PATHS.researchDiscover],
  [LEGACY_ROUTE_PATHS.backtest, APP_ROUTE_PATHS.researchBacktest],
  [LEGACY_ROUTE_PATHS.usage, APP_ROUTE_PATHS.settings],
];

const PRIMARY_NAV_TARGETS = APPLICATION_NAVIGATION_ITEMS.flatMap((item) => [
  item.to,
  ...(item.children?.map((child) => child.to) ?? []),
]);

describe('navigation IA route inventory', () => {
  it('keeps every primary-nav target on a canonical shell route', () => {
    for (const target of PRIMARY_NAV_TARGETS) {
      expect(CANONICAL_SHELL_ROUTES).toContain(target);
    }
  });

  it('does not expose orphan or legacy paths in product navigation', () => {
    for (const [legacyPath] of LEGACY_REDIRECT_MAP) {
      expect(PRIMARY_NAV_TARGETS).not.toContain(legacyPath);
    }
    expect(PRIMARY_NAV_TARGETS).not.toContain(APP_ROUTE_PATHS.signals);
    expect(PRIMARY_NAV_TARGETS).not.toContain(APP_ROUTE_PATHS.approvals);
    expect(PRIMARY_NAV_TARGETS).not.toContain(APP_ROUTE_PATHS.stockDetails);
    expect(PRIMARY_NAV_TARGETS).not.toContain(APP_ROUTE_PATHS.playground);
  });

  it('documents the full legacy redirect map for moved surfaces', () => {
    expect(LEGACY_REDIRECT_MAP).toEqual([
      ['/decision-signals', '/signals'],
      ['/alerts', '/signals'],
      ['/screening', '/research/discover'],
      ['/backtest', '/research/backtest'],
      ['/usage', '/settings'],
    ]);
    expect(Object.values(LEGACY_ROUTE_PATHS).sort()).toEqual(
      LEGACY_REDIRECT_MAP.map(([legacy]) => legacy).sort(),
    );
  });

  it('lists reachable surfaces that intentionally stay outside the primary sidebar', () => {
    const sidebarLinked = new Set(PRIMARY_NAV_TARGETS);
    const reachableOutsideSidebar = [
      APP_ROUTE_PATHS.signals,
      APP_ROUTE_PATHS.approvals,
      APP_ROUTE_PATHS.stockDetails,
      APP_ROUTE_PATHS.login,
      APP_ROUTE_PATHS.playground,
    ];
    for (const path of reachableOutsideSidebar) {
      expect(sidebarLinked.has(path)).toBe(false);
    }
  });
});
