/**
 * Client scenario library for report sensitivity / what-if reuse (Issue #1136).
 * Built-ins load from scenarioLibraryBuiltins.json (byte-identical mirror of
 * src/agent/scenario_library_builtins.json). Custom scenarios persist in localStorage.
 */
import builtinsCatalog from './scenarioLibraryBuiltins.json';
import {
  DEFAULT_WHAT_IF_MAX_TURNS,
  type WhatIfAssumption,
  type WhatIfDimension,
  type WhatIfDirection,
  type WhatIfDraftState,
  type WhatIfScenarioPayload,
} from './whatIfScenario';

export const SCENARIO_LIBRARY_VERSION =
  typeof builtinsCatalog.catalog_version === 'string' && builtinsCatalog.catalog_version
    ? builtinsCatalog.catalog_version
    : '1.0.0';
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

function asCategory(value: unknown): ScenarioCategory {
  if (value === 'rate' || value === 'fx' || value === 'industry' || value === 'market' || value === 'custom') {
    return value;
  }
  return 'custom';
}

function asRiskFraming(raw: unknown): ScenarioRiskFraming {
  const value = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const uncertainty = value.uncertainty_level;
  const sizing = value.position_sizing;
  return {
    uncertainty_level:
      uncertainty === 'baseline' || uncertainty === 'elevated' || uncertainty === 'high'
        ? uncertainty
        : 'elevated',
    position_sizing:
      sizing === 'unchanged' || sizing === 'tighter' || sizing === 'defensive' ? sizing : 'tighter',
    emphasis: Array.isArray(value.emphasis) ? value.emphasis.map(String) : [],
    tighter_constraints: Array.isArray(value.tighter_constraints)
      ? value.tighter_constraints.map(String)
      : [],
    section_deltas: Array.isArray(value.section_deltas)
      ? value.section_deltas
          .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
          .map((item) => ({
            section: String(item.section || ''),
            direction: String(item.direction || ''),
            note: String(item.note || ''),
          }))
      : [],
  };
}

function asAssumption(raw: unknown): WhatIfAssumption | null {
  if (!raw || typeof raw !== 'object') return null;
  const item = raw as Record<string, unknown>;
  const dimension = String(item.dimension || '') as WhatIfDimension;
  if (!dimension) return null;
  const out: WhatIfAssumption = { dimension };
  if (item.direction != null && item.direction !== '') {
    out.direction = String(item.direction) as WhatIfDirection;
  }
  if (typeof item.magnitude === 'number' && Number.isFinite(item.magnitude)) {
    out.magnitude = item.magnitude;
  }
  if (item.currency_pair != null && String(item.currency_pair).trim()) {
    out.currency_pair = String(item.currency_pair);
  }
  if (item.label != null && String(item.label).trim()) {
    out.label = String(item.label);
  }
  return out;
}

function loadBuiltins(): LibraryScenario[] {
  const scenarios = Array.isArray(builtinsCatalog.scenarios) ? builtinsCatalog.scenarios : [];
  const out: LibraryScenario[] = [];
  for (const raw of scenarios) {
    if (!raw || typeof raw !== 'object') continue;
    const item = raw as Record<string, unknown>;
    const assumptions = Array.isArray(item.assumptions)
      ? item.assumptions.map(asAssumption).filter((a): a is WhatIfAssumption => a != null)
      : [];
    if (!assumptions.length || !item.id) continue;
    out.push({
      id: String(item.id),
      name: String(item.name || item.id),
      description: String(item.description || ''),
      category: asCategory(item.category),
      markets: Array.isArray(item.markets) ? item.markets.map(String) : ['all'],
      assumptions,
      risk_framing: asRiskFraming(item.risk_framing),
      source: 'built_in',
      version: typeof item.version === 'number' ? item.version : 1,
    });
  }
  return out;
}

const BUILTIN: LibraryScenario[] = loadBuiltins();

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
  return BUILTIN.map((item) => ({
    ...item,
    assumptions: item.assumptions.map((a) => ({ ...a })),
    risk_framing: {
      ...item.risk_framing,
      emphasis: [...item.risk_framing.emphasis],
      tighter_constraints: [...item.risk_framing.tighter_constraints],
      section_deltas: item.risk_framing.section_deltas.map((d) => ({ ...d })),
    },
  }));
}

export function isBuiltinScenarioId(id: string | null | undefined): boolean {
  if (!id) return false;
  return BUILTIN.some((item) => item.id === id);
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
  if (isBuiltinScenarioId(id)) {
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
): {
  id: string;
  name: string;
  description?: string;
  category: ScenarioCategory;
  assumptions: WhatIfAssumption[];
} | null {
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

/**
 * Attach library metadata only for built-in scenario ids that the server catalog knows.
 * Custom (localStorage) scenarios send assumptions alone so the server never receives
 * an unknown scenario_id that would silently skip library framing.
 */
export function attachLibraryMetaToWhatIfPayload(
  payload: WhatIfScenarioPayload,
  scenarioId: string | null | undefined,
): WhatIfScenarioPayload {
  if (!scenarioId || !isBuiltinScenarioId(scenarioId)) {
    const next = { ...payload };
    delete next.scenario_id;
    delete next.catalog_version;
    delete next.scenario_hash;
    return next;
  }
  return {
    ...payload,
    scenario_id: scenarioId,
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
