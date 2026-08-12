/**
 * Client scenario library for report sensitivity / what-if reuse (Issue #1136).
 * Built-ins mirror the backend catalog; custom scenarios persist in localStorage.
 */
import {
  DEFAULT_WHAT_IF_MAX_TURNS,
  type WhatIfAssumption,
  type WhatIfDimension,
  type WhatIfDirection,
  type WhatIfDraftState,
  type WhatIfScenarioPayload,
} from './whatIfScenario';

export const SCENARIO_LIBRARY_VERSION = '1.0.0';
export const SCENARIO_LIBRARY_STORAGE_KEY = 'dsa.scenarioLibrary.custom.v1';

export type ScenarioCategory = 'rate' | 'fx' | 'industry' | 'market' | 'custom';

export interface ScenarioRiskFraming {
  uncertainty_level: 'baseline' | 'elevated' | 'high';
  position_sizing: 'unchanged' | 'tighter' | 'defensive';
  emphasis: string[];
  tighter_constraints: string[];
  section_deltas: Array<{ section: string; direction: string; note: string }>;
}

export interface LibraryScenario {
  id: string;
  name: string;
  description: string;
  category: ScenarioCategory;
  markets: string[];
  assumptions: WhatIfAssumption[];
  risk_framing: ScenarioRiskFraming;
  source: 'built_in' | 'custom';
  version: number;
}

const BUILTIN: LibraryScenario[] = [
  {
    id: 'rate_hike_100bp',
    name: 'Policy rates +100bp',
    description: 'Parallel policy-rate hike of 100 basis points.',
    category: 'rate',
    markets: ['all'],
    assumptions: [{ dimension: 'interest_rate', direction: 'up', magnitude: 100 }],
    risk_framing: {
      uncertainty_level: 'elevated',
      position_sizing: 'tighter',
      emphasis: ['discount_rate_pressure', 'duration_and_leverage_sensitivity'],
      tighter_constraints: [
        'Require explicit funding-cost and multiple-compression checks before any bullish sizing.',
      ],
      section_deltas: [
        { section: 'risks_counter_evidence', direction: 'elevated', note: 'Surface rate-driven downside.' },
        { section: 'risk_control', direction: 'tightened', note: 'Prefer smaller size under higher rates.' },
      ],
    },
    source: 'built_in',
    version: 1,
  },
  {
    id: 'rate_cut_50bp',
    name: 'Policy rates -50bp',
    description: 'Parallel policy-rate cut of 50 basis points.',
    category: 'rate',
    markets: ['all'],
    assumptions: [{ dimension: 'interest_rate', direction: 'down', magnitude: 50 }],
    risk_framing: {
      uncertainty_level: 'elevated',
      position_sizing: 'unchanged',
      emphasis: ['easing_is_not_risk_free', 'growth_reacceleration_vs_policy_lag'],
      tighter_constraints: ['Do not present rate cuts as guaranteed upside.'],
      section_deltas: [
        { section: 'risk_warning', direction: 'elevated', note: 'Mark easing benefits as hypothetical.' },
      ],
    },
    source: 'built_in',
    version: 1,
  },
  {
    id: 'fx_usd_cny_up_5',
    name: 'USD/CNY +5%',
    description: 'USD strengthens 5% versus CNY.',
    category: 'fx',
    markets: ['cn', 'hk', 'us'],
    assumptions: [{ dimension: 'fx_rate', direction: 'up', magnitude: 5, currency_pair: 'USD/CNY' }],
    risk_framing: {
      uncertainty_level: 'elevated',
      position_sizing: 'tighter',
      emphasis: ['import_cost_and_margin_pressure', 'capital_flow_sensitivity'],
      tighter_constraints: ['Call out FX exposure before upgrading confidence.'],
      section_deltas: [
        { section: 'risks_counter_evidence', direction: 'elevated', note: 'Emphasize FX drag.' },
      ],
    },
    source: 'built_in',
    version: 1,
  },
  {
    id: 'fx_usd_cny_down_5',
    name: 'USD/CNY -5%',
    description: 'USD weakens 5% versus CNY.',
    category: 'fx',
    markets: ['cn', 'hk', 'us'],
    assumptions: [{ dimension: 'fx_rate', direction: 'down', magnitude: 5, currency_pair: 'USD/CNY' }],
    risk_framing: {
      uncertainty_level: 'elevated',
      position_sizing: 'unchanged',
      emphasis: ['export_competitiveness_shift', 'fx_is_hypothetical_not_print'],
      tighter_constraints: ['Do not treat a weaker USD as confirmed bullish evidence.'],
      section_deltas: [
        { section: 'risk_warning', direction: 'elevated', note: 'Label FX path as scenario-only.' },
      ],
    },
    source: 'built_in',
    version: 1,
  },
  {
    id: 'industry_shock_down_15',
    name: 'Industry shock -15%',
    description: 'Sector / industry factor shock of -15%.',
    category: 'industry',
    markets: ['all'],
    assumptions: [
      {
        dimension: 'sector_shock',
        direction: 'down',
        magnitude: 15,
        label: 'Target industry / sector instantaneous -15%',
      },
    ],
    risk_framing: {
      uncertainty_level: 'high',
      position_sizing: 'defensive',
      emphasis: ['sector_beta_and_peer_contagion', 'thesis_invalidation_speed'],
      tighter_constraints: ['Prefer defensive sizing under industry shock.'],
      section_deltas: [
        { section: 'risk_control', direction: 'tightened', note: 'Defensive size under sector stress.' },
        { section: 'time_sensitivity', direction: 'accelerated', note: 'Shorten reaction window.' },
      ],
    },
    source: 'built_in',
    version: 1,
  },
  {
    id: 'market_down_10',
    name: 'Broad market -10%',
    description: 'Broad equity index instantaneous move of -10%.',
    category: 'market',
    markets: ['all'],
    assumptions: [{ dimension: 'index_move', direction: 'down', magnitude: 10 }],
    risk_framing: {
      uncertainty_level: 'high',
      position_sizing: 'defensive',
      emphasis: ['beta_and_correlation_spike', 'preserve_downside_first_framing'],
      tighter_constraints: ['Keep downside and liquidity risk ahead of opportunity framing.'],
      section_deltas: [
        { section: 'risks_counter_evidence', direction: 'elevated', note: 'Prioritize market-beta risk.' },
      ],
    },
    source: 'built_in',
    version: 1,
  },
];

function readStorage(): LibraryScenario[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(SCENARIO_LIBRARY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isLibraryScenario);
  } catch {
    return [];
  }
}

function writeStorage(items: LibraryScenario[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(SCENARIO_LIBRARY_STORAGE_KEY, JSON.stringify(items));
  } catch {
    // Best-effort persistence; in-memory still works for the session.
  }
}

function isLibraryScenario(value: unknown): value is LibraryScenario {
  if (!value || typeof value !== 'object') return false;
  const item = value as LibraryScenario;
  return typeof item.id === 'string' && Array.isArray(item.assumptions) && item.assumptions.length > 0;
}

export function listBuiltinScenarios(): LibraryScenario[] {
  return BUILTIN.map((item) => ({ ...item, assumptions: item.assumptions.map((a) => ({ ...a })) }));
}

export function listCustomScenarios(): LibraryScenario[] {
  return readStorage();
}

export function listAllScenarios(): LibraryScenario[] {
  return [...listBuiltinScenarios(), ...listCustomScenarios()];
}

export function getScenarioById(id: string): LibraryScenario | null {
  return listAllScenarios().find((item) => item.id === id) ?? null;
}

export function saveCustomScenario(input: {
  id: string;
  name: string;
  description?: string;
  category?: ScenarioCategory;
  assumptions: WhatIfAssumption[];
}): LibraryScenario {
  const id = input.id.trim().toLowerCase();
  if (!/^[a-z][a-z0-9_]{1,63}$/.test(id)) {
    throw new Error('invalid_scenario_id');
  }
  if (BUILTIN.some((item) => item.id === id)) {
    throw new Error('cannot_overwrite_builtin');
  }
  if (!input.assumptions.length) {
    throw new Error('assumptions_required');
  }
  const scenario: LibraryScenario = {
    id,
    name: input.name.trim() || id,
    description: (input.description || '').trim(),
    category: input.category || 'custom',
    markets: ['all'],
    assumptions: input.assumptions,
    risk_framing: {
      uncertainty_level: 'elevated',
      position_sizing: 'tighter',
      emphasis: ['hypothetical_path_only', 'keep_baseline_separate'],
      tighter_constraints: [
        'Scenario output is hypothetical; do not merge into baseline conclusions.',
      ],
      section_deltas: [
        {
          section: 'risk_warning',
          direction: 'elevated',
          note: 'Label results as hypothetical scenario analysis.',
        },
      ],
    },
    source: 'custom',
    version: 1,
  };
  const existing = readStorage().filter((item) => item.id !== id);
  writeStorage([...existing, scenario]);
  return scenario;
}

export function deleteCustomScenario(id: string): boolean {
  const before = readStorage();
  const next = before.filter((item) => item.id !== id);
  if (next.length === before.length) return false;
  writeStorage(next);
  return true;
}

export function applyScenarioToDraft(
  scenario: LibraryScenario,
  draft: WhatIfDraftState,
): WhatIfDraftState {
  const assumption = scenario.assumptions[0];
  if (!assumption) return { ...draft, enabled: true, scenarioId: scenario.id };
  const dimension = assumption.dimension as WhatIfDimension;
  const direction = (assumption.direction || 'down') as WhatIfDirection;
  return {
    ...draft,
    enabled: true,
    dimension,
    direction,
    magnitude:
      assumption.magnitude !== undefined && assumption.magnitude !== null
        ? String(assumption.magnitude)
        : draft.magnitude,
    currencyPair: assumption.currency_pair || draft.currencyPair || 'USD/CNY',
    scenarioId: scenario.id,
  };
}

export function draftToCustomScenarioInput(
  draft: WhatIfDraftState,
  meta: { id: string; name: string; description?: string },
): { id: string; name: string; description?: string; category: ScenarioCategory; assumptions: WhatIfAssumption[] } | null {
  if (!draft.enabled) return null;
  const assumption = buildAssumptionFromDraft(draft);
  if (!assumption) return null;
  const category: ScenarioCategory =
    draft.dimension === 'interest_rate'
      ? 'rate'
      : draft.dimension === 'fx_rate'
        ? 'fx'
        : draft.dimension === 'sector_shock'
          ? 'industry'
          : draft.dimension === 'index_move'
            ? 'market'
            : 'custom';
  return {
    id: meta.id,
    name: meta.name,
    description: meta.description,
    category,
    assumptions: [assumption],
  };
}

function buildAssumptionFromDraft(draft: WhatIfDraftState): WhatIfAssumption | null {
  if (draft.dimension === 'earnings') {
    if (draft.direction !== 'beat' && draft.direction !== 'miss' && draft.direction !== 'inline') return null;
    return { dimension: 'earnings', direction: draft.direction };
  }
  const magnitude = Number.parseFloat(draft.magnitude);
  if (!Number.isFinite(magnitude) || magnitude <= 0) return null;
  if (draft.direction !== 'up' && draft.direction !== 'down') return null;
  if (draft.dimension === 'fx_rate') {
    return {
      dimension: 'fx_rate',
      direction: draft.direction,
      magnitude,
      currency_pair: draft.currencyPair.trim() || 'USD/CNY',
    };
  }
  return { dimension: draft.dimension, direction: draft.direction, magnitude };
}

export function projectClientSensitivity(scenario: LibraryScenario): {
  catalog_version: string;
  scenario: LibraryScenario;
  risk_framing: ScenarioRiskFraming;
  hypothetical: true;
  summary: string;
} {
  return {
    catalog_version: SCENARIO_LIBRARY_VERSION,
    scenario,
    risk_framing: scenario.risk_framing,
    hypothetical: true,
    summary: `[HYPOTHETICAL SCENARIO] Under '${scenario.name}', uncertainty=${scenario.risk_framing.uncertainty_level}, position_sizing=${scenario.risk_framing.position_sizing}. Do not mix with baseline conclusions.`,
  };
}

export function mergeLibraryScenarioIntoWhatIfPayload(
  payload: WhatIfScenarioPayload,
  scenario: LibraryScenario | null,
): WhatIfScenarioPayload {
  if (!scenario) return payload;
  return {
    ...payload,
    assumptions: scenario.assumptions.length ? scenario.assumptions : payload.assumptions,
    scenario_id: scenario.id,
    catalog_version: SCENARIO_LIBRARY_VERSION,
  };
}

export function emptyCustomScenarioIdFromName(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 48);
  if (!slug) return `custom_${Date.now().toString(36)}`;
  return /^[a-z]/.test(slug) ? slug : `c_${slug}`;
}

export { DEFAULT_WHAT_IF_MAX_TURNS };
