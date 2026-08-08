// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Screening / Discover selection URL surface (UI-03A / #879 A1).
 *
 * Wire keys (stable once published):
 * - `candidate` — expanded result row (push)
 * - `hotspot` — selected hotspot topic (push)
 * - `hotspots` — section expanded flag (replace)
 *
 * Run filters (`market` / `strategy` / `count`) remain on researchRouteState
 * (task restore + explicit-default authority). Compose via
 * `composeScreeningHref` so filter writes preserve selection keys.
 */
import {
  getScreeningRunParametersLocation,
  type ScreeningRunParameters,
} from '../components/screening/screeningRunState';
import {
  booleanParam,
  defineUrlStateSchema,
  optionalStringParam,
  readParams,
  writeParams,
  type InferUrlState,
  type UrlHistoryMode,
  type UrlStatePatch,
} from '../utils/urlState';

export const screeningUrlSchema = defineUrlStateSchema({
  candidate: optionalStringParam({ name: 'candidate', history: 'push' }),
  hotspot: optionalStringParam({ name: 'hotspot', history: 'push' }),
  hotspotsOpen: booleanParam({ name: 'hotspots', default: false, history: 'replace' }),
});

export type ScreeningUrlState = InferUrlState<typeof screeningUrlSchema>;
export type ScreeningUrlPatch = UrlStatePatch<typeof screeningUrlSchema>;

export function readScreeningSelectionFromSearch(search: string): ScreeningUrlState {
  const values = readParams(screeningUrlSchema, search);
  return values.hotspot && !values.hotspotsOpen ? { ...values, hotspotsOpen: true } : values;
}

export function composeScreeningHref(
  runParameters: ScreeningRunParameters,
  selectionPatch: ScreeningUrlPatch,
  options: { history?: UrlHistoryMode } = {},
): { href: string; search: string; history: UrlHistoryMode } | null {
  const filterLocation = getScreeningRunParametersLocation(runParameters);
  if (!filterLocation) return null;
  const filterUrl = new URL(filterLocation, 'http://stockpulse.local');
  const next = writeParams(screeningUrlSchema, selectionPatch, {
    search: filterUrl.search,
    history: options.history,
  });
  return {
    href: `${filterUrl.pathname}${next.search}${filterUrl.hash}`,
    search: next.search,
    history: next.history,
  };
}
