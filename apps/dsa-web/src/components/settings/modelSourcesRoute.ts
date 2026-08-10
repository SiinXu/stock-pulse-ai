// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Route contract for the Model Sources setup flow.
 * Lives on Settings (`/settings`) so existing deep links and autosave stay intact.
 */

import {
  APP_ROUTE_PATHS,
  SETTINGS_ROUTE_QUERY_KEYS,
  SETTINGS_SECTION_IDS,
  SETTINGS_VIEW_IDS,
  buildSettingsHref,
} from '../../routing/routes';

export const MODEL_SOURCE_SETUP_QUERY_KEYS = {
  setup: 'setup',
  sourceType: 'sourceType',
  connection: 'connection',
  step: 'step',
} as const;

export const MODEL_SOURCE_SETUP_VALUES = {
  active: '1',
} as const;

export const MODEL_SOURCE_TYPES = {
  cloud: 'cloud',
  localServer: 'local_server',
  localCli: 'local_cli',
} as const;

export type ModelSourceType = (typeof MODEL_SOURCE_TYPES)[keyof typeof MODEL_SOURCE_TYPES];

export const MODEL_SOURCE_STEPS = {
  type: 'type',
  provider: 'provider',
  connect: 'connect',
  models: 'models',
  assign: 'assign',
} as const;

export type ModelSourceStep = (typeof MODEL_SOURCE_STEPS)[keyof typeof MODEL_SOURCE_STEPS];

export type ModelSourceSetupSearch = {
  sourceType?: ModelSourceType | null;
  connection?: string | null;
  step?: ModelSourceStep | null;
};

export function isModelSourceType(value: string | null | undefined): value is ModelSourceType {
  return value === MODEL_SOURCE_TYPES.cloud
    || value === MODEL_SOURCE_TYPES.localServer
    || value === MODEL_SOURCE_TYPES.localCli;
}

export function isModelSourceStep(value: string | null | undefined): value is ModelSourceStep {
  return value === MODEL_SOURCE_STEPS.type
    || value === MODEL_SOURCE_STEPS.provider
    || value === MODEL_SOURCE_STEPS.connect
    || value === MODEL_SOURCE_STEPS.models
    || value === MODEL_SOURCE_STEPS.assign;
}

export function isModelSourceSetupActive(searchParams: URLSearchParams): boolean {
  return searchParams.get(MODEL_SOURCE_SETUP_QUERY_KEYS.setup) === MODEL_SOURCE_SETUP_VALUES.active;
}

export function readModelSourceSetup(searchParams: URLSearchParams): ModelSourceSetupSearch & {
  active: boolean;
} {
  const sourceTypeRaw = searchParams.get(MODEL_SOURCE_SETUP_QUERY_KEYS.sourceType);
  const stepRaw = searchParams.get(MODEL_SOURCE_SETUP_QUERY_KEYS.step);
  return {
    active: isModelSourceSetupActive(searchParams),
    sourceType: isModelSourceType(sourceTypeRaw) ? sourceTypeRaw : null,
    connection: searchParams.get(MODEL_SOURCE_SETUP_QUERY_KEYS.connection),
    step: isModelSourceStep(stepRaw) ? stepRaw : null,
  };
}

export function buildModelSourceSetupHref(options: ModelSourceSetupSearch = {}): string {
  const base = buildSettingsHref({
    section: SETTINGS_SECTION_IDS.aiModels,
    view: SETTINGS_VIEW_IDS.aiModels.connections,
  });
  const params = new URLSearchParams(base.includes('?') ? base.split('?')[1] : '');
  params.set(MODEL_SOURCE_SETUP_QUERY_KEYS.setup, MODEL_SOURCE_SETUP_VALUES.active);
  if (options.sourceType) {
    params.set(MODEL_SOURCE_SETUP_QUERY_KEYS.sourceType, options.sourceType);
  } else {
    params.delete(MODEL_SOURCE_SETUP_QUERY_KEYS.sourceType);
  }
  if (options.connection?.trim()) {
    params.set(MODEL_SOURCE_SETUP_QUERY_KEYS.connection, options.connection.trim());
  } else {
    params.delete(MODEL_SOURCE_SETUP_QUERY_KEYS.connection);
  }
  if (options.step) {
    params.set(MODEL_SOURCE_SETUP_QUERY_KEYS.step, options.step);
  } else {
    params.delete(MODEL_SOURCE_SETUP_QUERY_KEYS.step);
  }
  const query = params.toString();
  return query ? `${APP_ROUTE_PATHS.settings}?${query}` : APP_ROUTE_PATHS.settings;
}

export function clearModelSourceSetupParams(searchParams: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  next.delete(MODEL_SOURCE_SETUP_QUERY_KEYS.setup);
  next.delete(MODEL_SOURCE_SETUP_QUERY_KEYS.sourceType);
  next.delete(MODEL_SOURCE_SETUP_QUERY_KEYS.connection);
  next.delete(MODEL_SOURCE_SETUP_QUERY_KEYS.step);
  if (!next.get(SETTINGS_ROUTE_QUERY_KEYS.section)) {
    next.set(SETTINGS_ROUTE_QUERY_KEYS.section, SETTINGS_SECTION_IDS.aiModels);
  }
  if (!next.get(SETTINGS_ROUTE_QUERY_KEYS.view)) {
    next.set(SETTINGS_ROUTE_QUERY_KEYS.view, SETTINGS_VIEW_IDS.aiModels.connections);
  }
  return next;
}

export function applyModelSourceSetupParams(
  searchParams: URLSearchParams,
  options: ModelSourceSetupSearch & { active?: boolean } = {},
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  next.set(SETTINGS_ROUTE_QUERY_KEYS.section, SETTINGS_SECTION_IDS.aiModels);
  next.set(SETTINGS_ROUTE_QUERY_KEYS.view, SETTINGS_VIEW_IDS.aiModels.connections);
  if (options.active === false) {
    return clearModelSourceSetupParams(next);
  }
  next.set(MODEL_SOURCE_SETUP_QUERY_KEYS.setup, MODEL_SOURCE_SETUP_VALUES.active);
  if (options.sourceType) {
    next.set(MODEL_SOURCE_SETUP_QUERY_KEYS.sourceType, options.sourceType);
  }
  if (options.connection !== undefined) {
    if (options.connection?.trim()) {
      next.set(MODEL_SOURCE_SETUP_QUERY_KEYS.connection, options.connection.trim());
    } else {
      next.delete(MODEL_SOURCE_SETUP_QUERY_KEYS.connection);
    }
  }
  if (options.step) {
    next.set(MODEL_SOURCE_SETUP_QUERY_KEYS.step, options.step);
  }
  return next;
}
