// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  assertNonEmptyProductionInventory,
  productionTypeScriptSources,
} from '../../components/__tests__/productionSourceInventory';
import { APP_ROUTE_PATHS } from '../routes';
import {
  NAMED_BOARD_CAPABILITIES,
  UNREACHABLE_CAPABILITY_LEDGER,
  buildReachabilityInventory,
  buildValueImportConsumers,
  listRelativeValueImportSpecifiers,
  normalizeSrcRelativePath,
  parseAppRouteTable,
  resolveProductionRoute,
} from '../productionReachability';

function srcSources(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(productionTypeScriptSources).map(([key, source]) => [
      normalizeSrcRelativePath(key),
      source,
    ]),
  );
}

describe('production reachability inventory', () => {
  it('reads value imports after a leading newline without spanning later statements', () => {
    expect(listRelativeValueImportSpecifiers(
      "import type React from 'react';\nimport EventCalendarWorkspace from '../components/event-calendar/EventCalendarWorkspace';\nimport './App.css';\n",
    )).toEqual(['../components/event-calendar/EventCalendarWorkspace']);
  });

  it('lists every product surface and the route that reaches it', () => {
    assertNonEmptyProductionInventory(productionTypeScriptSources, 'productionTypeScriptSources');
    const sources = srcSources();
    const appSource = sources['App.tsx'];
    expect(appSource).toBeTruthy();
    const { reachable, unreachable } = buildReachabilityInventory(sources, appSource ?? '');

    expect(unreachable).toEqual(UNREACHABLE_CAPABILITY_LEDGER.map((entry) => entry.file).sort());
    expect(NAMED_BOARD_CAPABILITIES).toHaveLength(19);
    // Pin the mechanical inventory size so the PR body can quote counts.
    expect(reachable.length).toBe(74);

    const listed = reachable.map((entry) => `${entry.file} ${entry.route}`);
    expect(listed).toEqual([...listed].sort());

    for (const entry of reachable) {
      expect(entry.route.startsWith('/')).toBe(true);
      expect(Object.values(APP_ROUTE_PATHS)).toContain(entry.route);
    }
  });

  it('keeps every named #1058/#1008 board capability on a production route', () => {
    const sources = srcSources();
    const routeByModule = new Map(
      parseAppRouteTable(sources['App.tsx'] ?? '').map((binding) => [binding.module, binding]),
    );
    const consumers = buildValueImportConsumers(sources);
    const ledgerFiles = new Set(UNREACHABLE_CAPABILITY_LEDGER.map((entry) => entry.file));

    expect(NAMED_BOARD_CAPABILITIES).toHaveLength(19);
    for (const capability of NAMED_BOARD_CAPABILITIES) {
      expect(ledgerFiles.has(capability.file)).toBe(false);
      expect(sources[capability.file], capability.file).toBeTruthy();
      const routed = resolveProductionRoute(capability.file, consumers, routeByModule);
      expect(routed, capability.id).toBeDefined();
      expect(routed?.route.startsWith('/')).toBe(true);
    }
  });

  it('covers every non-playground App route path with at least one inventory row', () => {
    const sources = srcSources();
    const { reachable } = buildReachabilityInventory(sources, sources['App.tsx'] ?? '');
    const routedKeys = new Set(reachable.map((entry) => entry.routeKey));
    const productRouteKeys = Object.entries(APP_ROUTE_PATHS)
      .filter(([key]) => key !== 'playground' && key !== 'playgroundRender')
      .map(([key]) => key);

    for (const key of productRouteKeys) {
      expect(routedKeys.has(key), key).toBe(true);
    }
  });
});
