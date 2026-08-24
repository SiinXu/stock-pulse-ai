// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  assertNonEmptyProductionInventory,
  productionTypeScriptSources,
} from '../../components/__tests__/productionSourceInventory';
import { APP_ROUTE_PATHS } from '../routes';
import {
  APP_ROUTE_MODULE_SNAPSHOT,
  NAMED_BOARD_CAPABILITIES,
  UNREACHABLE_CAPABILITY_LEDGER,
  buildReachabilityInventory,
  formatReachableMapping,
  listRelativeValueImportSpecifiers,
  normalizeSrcRelativePath,
} from '../productionReachability';
import { REACHABLE_SURFACE_ROUTE_SNAPSHOT } from './productionReachabilitySnapshot';

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

  it('lists every product surface and the pinned route that reaches it', () => {
    assertNonEmptyProductionInventory(productionTypeScriptSources, 'productionTypeScriptSources');
    const sources = srcSources();
    const appSource = sources['App.tsx'];
    expect(appSource).toBeTruthy();
    const { reachable, unreachable } = buildReachabilityInventory(sources, appSource ?? '');

    expect(unreachable).toEqual(UNREACHABLE_CAPABILITY_LEDGER.map((entry) => entry.file).sort());
    expect(NAMED_BOARD_CAPABILITIES).toHaveLength(19);
    expect(formatReachableMapping(reachable)).toEqual(REACHABLE_SURFACE_ROUTE_SNAPSHOT);
    expect(reachable.length).toBe(REACHABLE_SURFACE_ROUTE_SNAPSHOT.length);

    for (const entry of reachable) {
      expect(entry.route).toBe(APP_ROUTE_PATHS[entry.routeKey as keyof typeof APP_ROUTE_PATHS]);
    }
  });

  it('covers every non-playground App route path with at least one inventory row', () => {
    const sources = srcSources();
    const { reachable } = buildReachabilityInventory(sources, sources['App.tsx'] ?? '');
    const routedKeys = new Set(reachable.map((entry) => entry.routeKey));
    for (const { routeKey } of APP_ROUTE_MODULE_SNAPSHOT) {
      expect(routedKeys.has(routeKey), routeKey).toBe(true);
    }
  });
});
