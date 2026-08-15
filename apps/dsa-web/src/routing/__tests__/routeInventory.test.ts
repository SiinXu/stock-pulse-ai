// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  APPLICATION_NAVIGATION_ITEMS,
  COMMAND_PALETTE_SECONDARY_PAGES,
  listCommandPalettePages,
} from '../../components/layout/navigation';
import { APP_ROUTE_PATHS, LEGACY_ROUTE_PATHS } from '../routes';

/**
 * Mechanical route inventory for Navigation IA (#368 / #873).
 * Keep this table aligned with App.tsx + APPLICATION_NAVIGATION_ITEMS.
 */
const PRIMARY_NAV_ROUTES = [
  APP_ROUTE_PATHS.home,
  APP_ROUTE_PATHS.research,
  APP_ROUTE_PATHS.researchMarket,
  APP_ROUTE_PATHS.researchDiscover,
  APP_ROUTE_PATHS.researchAnalysis,
  APP_ROUTE_PATHS.researchBacktest,
  APP_ROUTE_PATHS.eventCalendar,
  APP_ROUTE_PATHS.calculators,
  APP_ROUTE_PATHS.researchSkillOutcomes,
  APP_ROUTE_PATHS.agent,
  APP_ROUTE_PATHS.signals,
  APP_ROUTE_PATHS.portfolio,
  APP_ROUTE_PATHS.settings,
] as const;

const COMMAND_ENTRY_ROUTES = [
  APP_ROUTE_PATHS.approvals,
] as const;

const CONTEXT_ENTRY_ROUTES = [
  APP_ROUTE_PATHS.notifications,
  APP_ROUTE_PATHS.stockDetails,
  APP_ROUTE_PATHS.eventAlerts,
  APP_ROUTE_PATHS.portfolioPerformance,
  APP_ROUTE_PATHS.researchReportCompare,
] as const;

const STANDALONE_ROUTES = [
  APP_ROUTE_PATHS.login,
  APP_ROUTE_PATHS.playground,
  APP_ROUTE_PATHS.playgroundRender,
] as const;

const CANONICAL_SHELL_ROUTES = [
  APP_ROUTE_PATHS.home,
  APP_ROUTE_PATHS.agent,
  APP_ROUTE_PATHS.portfolio,
  APP_ROUTE_PATHS.signals,
  APP_ROUTE_PATHS.approvals,
  APP_ROUTE_PATHS.notifications,
  APP_ROUTE_PATHS.stockDetails,
  APP_ROUTE_PATHS.eventAlerts,
  APP_ROUTE_PATHS.portfolioPerformance,
  APP_ROUTE_PATHS.researchReportCompare,
  APP_ROUTE_PATHS.research,
  APP_ROUTE_PATHS.researchMarket,
  APP_ROUTE_PATHS.researchDiscover,
  APP_ROUTE_PATHS.researchAnalysis,
  APP_ROUTE_PATHS.researchBacktest,
  APP_ROUTE_PATHS.calculators,
  APP_ROUTE_PATHS.researchSkillOutcomes,
  APP_ROUTE_PATHS.eventCalendar,
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
    expect(PRIMARY_NAV_TARGETS).toEqual(PRIMARY_NAV_ROUTES);
    for (const target of PRIMARY_NAV_TARGETS) {
      expect(CANONICAL_SHELL_ROUTES).toContain(target);
    }
  });

  it('does not expose orphan or legacy paths in product navigation', () => {
    for (const [legacyPath] of LEGACY_REDIRECT_MAP) {
      expect(PRIMARY_NAV_TARGETS).not.toContain(legacyPath);
    }
    expect(PRIMARY_NAV_TARGETS).toContain(APP_ROUTE_PATHS.agent);
    expect(PRIMARY_NAV_TARGETS).not.toContain(APP_ROUTE_PATHS.approvals);
    expect(PRIMARY_NAV_TARGETS).not.toContain(APP_ROUTE_PATHS.stockDetails);
    expect(PRIMARY_NAV_TARGETS).not.toContain(APP_ROUTE_PATHS.playground);
    // Signals is first-class on the primary spine.
    expect(PRIMARY_NAV_TARGETS).toContain(APP_ROUTE_PATHS.signals);
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

  it('classifies every canonical route by its discoverability contract', () => {
    const sidebarLinked = new Set(PRIMARY_NAV_TARGETS);
    for (const path of [...COMMAND_ENTRY_ROUTES, ...CONTEXT_ENTRY_ROUTES, ...STANDALONE_ROUTES]) {
      expect(sidebarLinked.has(path)).toBe(false);
    }

    const classifiedRoutes = [
      ...PRIMARY_NAV_ROUTES,
      ...COMMAND_ENTRY_ROUTES,
      ...CONTEXT_ENTRY_ROUTES,
      ...STANDALONE_ROUTES,
    ];
    expect(new Set(classifiedRoutes).size).toBe(classifiedRoutes.length);
    expect([...classifiedRoutes].sort()).toEqual(Object.values(APP_ROUTE_PATHS).sort());
  });

  it('keeps command-palette page hrefs on canonical routes and includes secondary surfaces', () => {
    const paletteHrefs = listCommandPalettePages().map((page) => page.href);
    for (const href of paletteHrefs) {
      const path = href.split('?')[0] ?? href;
      expect([
        ...CANONICAL_SHELL_ROUTES,
        APP_ROUTE_PATHS.calculators,
      ]).toContain(path);
    }
    expect(paletteHrefs).toContain(APP_ROUTE_PATHS.signals);
    expect(paletteHrefs).toContain(APP_ROUTE_PATHS.agent);
    expect(paletteHrefs).toContain(APP_ROUTE_PATHS.approvals);
    expect(COMMAND_PALETTE_SECONDARY_PAGES.map((page) => page.to)).toEqual([
      APP_ROUTE_PATHS.approvals,
    ]);
  });

  it('keeps every legacy redirect target registered for shell routing', () => {
    for (const [, canonical] of LEGACY_REDIRECT_MAP) {
      expect(CANONICAL_SHELL_ROUTES).toContain(canonical);
    }
  });
});
