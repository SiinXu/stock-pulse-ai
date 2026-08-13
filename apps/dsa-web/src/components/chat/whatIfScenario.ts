/**
 * Structured what-if scenario helpers for Agent Chat (Issue #130).
 * Issue #1136 reuses this channel for the report sensitivity scenario library.
 * Free-text assumptions are intentionally out of scope for v1.
 */
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  buildAnalysisWorkbenchHref,
} from '../../routing/routes';
import builtinsCatalog from './scenarioLibraryBuiltins.json';

export const HYPOTHETICAL_ASSUMPTION_MARKER = '[HYPOTHETICAL ASSUMPTION]';
export const HYPOTHETICAL_RESULT_MARKER = '[HYPOTHETICAL SCENARIO]';
export const DEFAULT_WHAT_IF_MAX_TURNS = 5;

function isServerKnownLibraryScenarioId(scenarioId: string): boolean {
  const scenarios = Array.isArray(builtinsCatalog.scenarios) ? builtinsCatalog.scenarios : [];
  return scenarios.some(
    (item) => item && typeof item === 'object' && String((item as { id?: string }).id || '') === scenarioId,
  );
}

function libraryCatalogVersion(): string {
  return typeof builtinsCatalog.catalog_version === 'string' && builtinsCatalog.catalog_version
    ? builtinsCatalog.catalog_version
    : '1.0.0';
}
export type WhatIfDimension =
  | 'index_move'
  | 'fx_rate'
  | 'interest_rate'
  | 'earnings'
  | 'sector_shock';
export type WhatIfDirection = 'up' | 'down' | 'beat' | 'miss' | 'inline';
export interface WhatIfAssumption {
  dimension: WhatIfDimension;
  direction?: WhatIfDirection;
  magnitude?: number;
  currency_pair?: string;
  label?: string;
}
export interface WhatIfScenarioPayload {
  enabled: boolean;
  turn_index: number;
  max_turns: number;
  assumptions: WhatIfAssumption[];
  scenario_id?: string;
  catalog_version?: string;
  scenario_hash?: string;
}
export interface WhatIfDraftState {
  enabled: boolean;
  dimension: WhatIfDimension;
  direction: WhatIfDirection;
  magnitude: string;
  currencyPair: string;
  turnCount: number;
  /** Optional library scenario id applied via the #1136 scenario library. */
  scenarioId?: string | null;
}
export const DEFAULT_WHAT_IF_DRAFT: WhatIfDraftState = {
  enabled: false,
  dimension: 'interest_rate',
  direction: 'down',
  magnitude: '50',
  currencyPair: 'USD/CNY',
  turnCount: 0,
  scenarioId: null,
};
export function contentHasHypotheticalMarker(content: string | undefined | null): boolean {
  if (!content) return false;
  return content.includes(HYPOTHETICAL_RESULT_MARKER) || content.includes(HYPOTHETICAL_ASSUMPTION_MARKER);
}
export function parseMagnitude(raw: string): number | null {
  const value = Number.parseFloat(raw.trim());
  if (!Number.isFinite(value) || value <= 0) return null;
  return value;
}
export function buildWhatIfAssumption(draft: WhatIfDraftState): WhatIfAssumption | null {
  if (!draft.enabled) return null;
  if (draft.dimension === 'earnings') {
    if (draft.direction !== 'beat' && draft.direction !== 'miss' && draft.direction !== 'inline') return null;
    return { dimension: 'earnings', direction: draft.direction };
  }
  const magnitude = parseMagnitude(draft.magnitude);
  if (magnitude === null) return null;
  if (draft.direction !== 'up' && draft.direction !== 'down') return null;
  if (draft.dimension === 'fx_rate') {
    return { dimension: 'fx_rate', direction: draft.direction, magnitude, currency_pair: draft.currencyPair.trim() || 'USD/CNY' };
  }
  return { dimension: draft.dimension, direction: draft.direction, magnitude };
}
export function buildWhatIfContextPayload(draft: WhatIfDraftState): WhatIfScenarioPayload | null {
  const assumption = buildWhatIfAssumption(draft);
  if (!assumption || draft.turnCount >= DEFAULT_WHAT_IF_MAX_TURNS) return null;
  const payload: WhatIfScenarioPayload = {
    enabled: true,
    turn_index: draft.turnCount + 1,
    max_turns: DEFAULT_WHAT_IF_MAX_TURNS,
    assumptions: [assumption],
  };
  // Only built-in library ids are server-known. Custom localStorage scenarios
  // reuse the what-if assumptions channel without a scenario_id (Issue #1136).
  if (draft.scenarioId && isServerKnownLibraryScenarioId(draft.scenarioId)) {
    payload.scenario_id = draft.scenarioId;
    payload.catalog_version = libraryCatalogVersion();
  }
  return payload;
}
export function isWhatIfLimitReached(draft: WhatIfDraftState): boolean {
  return draft.enabled && draft.turnCount >= DEFAULT_WHAT_IF_MAX_TURNS;
}
export function mergeWhatIfIntoContext(
  baseContext: Record<string, unknown> | null | undefined,
  draft: WhatIfDraftState,
): Record<string, unknown> | undefined {
  const whatIf = buildWhatIfContextPayload(draft);
  if (!whatIf) return baseContext ?? undefined;
  return { ...(baseContext ?? {}), what_if: whatIf };
}
export function countWhatIfTurnsInMessages(messages: Array<{ role: string; content: string }>): number {
  return messages.filter((m) => m.role === 'user' && contentHasHypotheticalMarker(m.content)).length;
}

/**
 * Optional handoff from a what-if session to the analysis workbench launch UI.
 * Prefills stock only — does not auto-start a run and never injects hypothetical
 * assumptions (isolation: no DecisionSignal pollution from this handoff).
 */
export function buildWhatIfPromoteAnalysisHref(
  stockCode: string | null | undefined,
): string | null {
  const code = (stockCode || '').trim();
  if (!code) return null;
  return buildAnalysisWorkbenchHref({
    stock: code,
    segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
  });
}
