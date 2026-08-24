// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import {
  UNREACHABLE_CAPABILITY_LEDGER,
  UNREACHABLE_CAPABILITY_LEDGER_CEILING,
  assertCapabilityHostMentions,
  buildReachabilityInventory,
  normalizeSrcRelativePath,
  parseAppRouteTable,
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

  it('maps App.tsx lazy page modules onto canonical APP_ROUTE_PATHS', () => {
    const sources = srcSources();
    const bindings = parseAppRouteTable(sources['App.tsx'] ?? '');
    expect(bindings.length).toBeGreaterThan(15);
    for (const binding of bindings) {
      expect(binding.route).toBe(APP_ROUTE_PATHS[binding.routeKey as keyof typeof APP_ROUTE_PATHS]);
      expect(sources[binding.module], binding.module).toBeTruthy();
    }
    expect(bindings.some((binding) => binding.module.includes('playground'))).toBe(false);
  });
});
