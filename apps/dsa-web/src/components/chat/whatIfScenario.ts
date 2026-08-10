/**
 * Structured what-if scenario helpers for Agent Chat (Issue #130).
 * Free-text assumptions are intentionally out of scope for v1.
 */
export const HYPOTHETICAL_ASSUMPTION_MARKER = '[HYPOTHETICAL ASSUMPTION]';
export const HYPOTHETICAL_RESULT_MARKER = '[HYPOTHETICAL SCENARIO]';
export const DEFAULT_WHAT_IF_MAX_TURNS = 5;
export type WhatIfDimension = 'index_move' | 'fx_rate' | 'interest_rate' | 'earnings';
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
}
export interface WhatIfDraftState {
  enabled: boolean;
  dimension: WhatIfDimension;
  direction: WhatIfDirection;
  magnitude: string;
  currencyPair: string;
  turnCount: number;
}
export const DEFAULT_WHAT_IF_DRAFT: WhatIfDraftState = {
  enabled: false,
  dimension: 'interest_rate',
  direction: 'down',
  magnitude: '50',
  currencyPair: 'USD/CNY',
  turnCount: 0,
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
  return { enabled: true, turn_index: draft.turnCount + 1, max_turns: DEFAULT_WHAT_IF_MAX_TURNS, assumptions: [assumption] };
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
