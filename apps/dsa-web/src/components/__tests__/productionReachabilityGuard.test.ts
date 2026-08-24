// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import {
  APP_ROUTE_MODULE_SNAPSHOT,
  NAMED_BOARD_CAPABILITIES,
  UNREACHABLE_CAPABILITY_LEDGER,
  UNREACHABLE_CAPABILITY_LEDGER_CEILING,
  assertCapabilityHostMentions,
  buildReachabilityInventory,
  buildValueImportConsumers,
  normalizeSrcRelativePath,
  parseAppRouteTable,
  resolveProductionRoute,
} from '../../routing/productionReachability';
import {
  assertNonEmptyProductionInventory,
  productionTypeScriptSources,
} from './productionSourceInventory';

function srcSources(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(productionTypeScriptSources).map(([key, source]) => [
      normalizeSrcRelativePath(key),
      source,
    ]),
  );
}

describe('production reachability guard', () => {
  it('fails when a capability host no longer mentions the component', () => {
    expect(() => assertCapabilityHostMentions(
      'export default function HomePage() { return null; }',
      'TodaysFocusPanel',
      'todays-focus',
      'jsx',
    )).toThrow(/todays-focus/);
  });

  it('fails when a routed page module is removed from the App route table', () => {
    const appSource = `
      const HomePage = lazy(() => import('./pages/HomePage'));
      const SettingsPage = lazy(() => import('./pages/SettingsPage'));
      { path: APP_ROUTE_PATHS.settings, element: <SettingsPage /> }
    `;
    const bindings = parseAppRouteTable(appSource);
    expect(bindings.some((binding) => binding.module === 'pages/HomePage.tsx')).toBe(false);
    expect(bindings.map((binding) => binding.module)).toEqual(['pages/SettingsPage.tsx']);
  });

  it('marks a nested panel unreachable when its host page is unrouted', () => {
    const sources = {
      'App.tsx': `
        const SettingsPage = lazy(() => import('./pages/SettingsPage'));
        { path: APP_ROUTE_PATHS.settings, element: <SettingsPage /> }
      `,
      'pages/HomePage.tsx': `
        import { TodaysFocusPanel } from '../components/home/TodaysFocusPanel';
        export default function HomePage() { return <TodaysFocusPanel />; }
      `,
      'pages/SettingsPage.tsx': 'export default function SettingsPage() { return null; }',
      'components/home/TodaysFocusPanel.tsx': 'export const TodaysFocusPanel = () => null;',
    };
    const { reachable, unreachable } = buildReachabilityInventory(sources, sources['App.tsx']);
    expect(unreachable).toContain('components/home/TodaysFocusPanel.tsx');
    expect(unreachable).toContain('pages/HomePage.tsx');
    expect(reachable.map((entry) => entry.file)).toEqual(['pages/SettingsPage.tsx']);
  });

  it('does not treat export-star barrel importers as hosts of unmentioned widgets', () => {
    const sources = {
      'App.tsx': `
        const HomePage = lazy(() => import('./pages/HomePage'));
        const MarketReviewPage = lazy(() => import('./pages/MarketReviewPage'));
        { path: APP_ROUTE_PATHS.home, element: <HomePage /> }
        { path: APP_ROUTE_PATHS.researchMarket, element: <MarketReviewPage /> }
      `,
      'pages/HomePage.tsx': 'export default function HomePage() { return null; }',
      'pages/MarketReviewPage.tsx': `
        import { DashboardStateBlock } from '../components/dashboard';
        export default function MarketReviewPage() { return <DashboardStateBlock />; }
      `,
      'components/dashboard/index.ts': `
        export * from './DashboardStateBlock';
        export * from './HomePortfolioHealthWidget';
      `,
      'components/dashboard/DashboardStateBlock.tsx': 'export const DashboardStateBlock = () => null;',
      'components/dashboard/HomePortfolioHealthWidget.tsx':
        'export const HomePortfolioHealthWidget = () => null;',
    };
    const consumers = buildValueImportConsumers(sources);
    const routeByModule = new Map(
      parseAppRouteTable(sources['App.tsx']).map((binding) => [binding.module, binding]),
    );
    expect(
      resolveProductionRoute(
        'components/dashboard/HomePortfolioHealthWidget.tsx',
        consumers,
        routeByModule,
      ),
    ).toBeUndefined();
    expect(
      resolveProductionRoute(
        'components/dashboard/DashboardStateBlock.tsx',
        consumers,
        routeByModule,
      )?.routeKey,
    ).toBe('researchMarket');
    const { unreachable } = buildReachabilityInventory(sources, sources['App.tsx']);
    expect(unreachable).toContain('components/dashboard/HomePortfolioHealthWidget.tsx');
    expect(() => assertCapabilityHostMentions(
      sources['pages/HomePage.tsx'] ?? '',
      'HomePortfolioHealthWidget',
      'home-portfolio-health',
      'jsx',
    )).toThrow(/home-portfolio-health/);
  });

  it('does not treat a settings barrel importer as the DataProvidersPanel host', () => {
    const sources = {
      'App.tsx': `
        const SettingsPage = lazy(() => import('./pages/SettingsPage'));
        { path: APP_ROUTE_PATHS.settings, element: <SettingsPage /> }
      `,
      'pages/SettingsPage.tsx': `
        import { SettingsField } from '../components/settings';
        export default function SettingsPage() { return <SettingsField />; }
      `,
      'components/settings/index.ts': `
        export * from './SettingsField';
        export * from './DataProvidersPanel';
      `,
      'components/settings/SettingsField.tsx': 'export const SettingsField = () => null;',
      'components/settings/DataProvidersPanel.tsx': 'export const DataProvidersPanel = () => null;',
      'components/settings/SettingsActiveConfigPanel.tsx':
        'export const SettingsActiveConfigPanel = () => null;',
    };
    const consumers = buildValueImportConsumers(sources);
    const routeByModule = new Map(
      parseAppRouteTable(sources['App.tsx']).map((binding) => [binding.module, binding]),
    );
    expect(
      resolveProductionRoute(
        'components/settings/DataProvidersPanel.tsx',
        consumers,
        routeByModule,
      ),
    ).toBeUndefined();
    expect(() => assertCapabilityHostMentions(
      sources['components/settings/SettingsActiveConfigPanel.tsx'] ?? '',
      'DataProvidersPanel',
      'data-providers',
      'jsx',
    )).toThrow(/data-providers/);
  });

  it('keeps currently-unreachable surfaces on a shrink-only ledger', () => {
    assertNonEmptyProductionInventory(productionTypeScriptSources, 'productionTypeScriptSources');
    const sources = srcSources();
    const { unreachable } = buildReachabilityInventory(sources, sources['App.tsx'] ?? '');

    expect(UNREACHABLE_CAPABILITY_LEDGER.length).toBeLessThanOrEqual(
      UNREACHABLE_CAPABILITY_LEDGER_CEILING,
    );
    expect(unreachable).toEqual(UNREACHABLE_CAPABILITY_LEDGER.map((entry) => entry.file).sort());
    for (const entry of UNREACHABLE_CAPABILITY_LEDGER) {
      expect(entry.reason.trim().length).toBeGreaterThan(0);
      expect(entry.removeWhen.trim().length).toBeGreaterThan(0);
      expect(sources[entry.file], entry.file).toBeTruthy();
    }
  });

  it('maps App.tsx lazy page modules onto the pinned route snapshot', () => {
    const sources = srcSources();
    const bindings = parseAppRouteTable(sources['App.tsx'] ?? '');
    expect(
      bindings.map((binding) => ({ module: binding.module, routeKey: binding.routeKey })),
    ).toEqual([...APP_ROUTE_MODULE_SNAPSHOT]);
    for (const binding of bindings) {
      expect(binding.route).toBe(APP_ROUTE_PATHS[binding.routeKey as keyof typeof APP_ROUTE_PATHS]);
      expect(sources[binding.module], binding.module).toBeTruthy();
    }
    expect(bindings.some((binding) => binding.module.includes('playground'))).toBe(false);
  });

  it('asserts live host usage and pinned routes for every named board capability', () => {
    const sources = srcSources();
    const consumers = buildValueImportConsumers(sources);
    const routeByModule = new Map(
      parseAppRouteTable(sources['App.tsx'] ?? '').map((binding) => [binding.module, binding]),
    );
    expect(NAMED_BOARD_CAPABILITIES).toHaveLength(19);
    for (const capability of NAMED_BOARD_CAPABILITIES) {
      const hostSource = sources[capability.host];
      expect(hostSource, capability.host).toBeTruthy();
      assertCapabilityHostMentions(
        hostSource ?? '',
        capability.hostMention,
        capability.id,
        capability.hostUsage,
      );
      const routed = capability.host === 'App.tsx'
        ? routeByModule.get(capability.file)
        : routeByModule.get(capability.host)
          ?? resolveProductionRoute(capability.host, consumers, routeByModule);
      expect(routed?.routeKey, capability.id).toBe(capability.routeKey);
      expect(routed?.route).toBe(APP_ROUTE_PATHS[capability.routeKey]);
    }
  });
});
