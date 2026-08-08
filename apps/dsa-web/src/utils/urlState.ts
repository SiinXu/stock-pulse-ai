// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Shared URL search-param state helper (UI-03A / issue #879 A1 foundation).
 *
 * ## Why this module exists
 *
 * URL ownership is currently split across three styles:
 * 1. React Router `useSearchParams` / `navigate` (Home/Settings/Chat/Stock/Portfolio)
 * 2. Mount-time search reads + ad-hoc writers (Decision Signals filters, Screening/Backtest)
 * 3. Mostly local React state with little or no shareable URL surface (parts of Alerts/Usage)
 *
 * Full page migration cannot land in one PR. This module only defines the **contract**:
 * typed schemas, pure read/write, history mode rules, and unknown-key preservation.
 * Page wiring is intentionally out of scope (later migration waves).
 *
 * ## Migration guide
 *
 * 1. **Migrate first** pages that lose filters, tabs, or selection on refresh/share/back
 *    (Signals list/timeline params, Discover/Backtest filters that are mount-only,
 *    Portfolio/Alerts surfaces that still rely on local-only state for shareable intent).
 * 2. **Defer** pages that already keep durable state in Router search params and have
 *    dedicated parsers (`homeUrlState`, `signalCenterRouteState`, Settings section keys).
 * 3. Declare a page schema with name, parse/serialize, default, and `history` per param.
 * 4. On mount / `location.search` change: `const values = readParams(schema, location.search)`.
 * 5. On user action:
 *    ```ts
 *    const next = writeParams(schema, patch, { search: location.search });
 *    navigate(
 *      { pathname: location.pathname, search: next.search, hash: location.hash },
 *      { replace: next.history === 'replace' },
 *    );
 *    ```
 * 6. Or with `setSearchParams`: `setSearchParams(next.params, { replace: next.history === 'replace' })`.
 * 7. **Never** put shareable intent in `location.state`. Only ephemeral session flags
 *    (for example restore suppression) belong there. Shareable intent must be query params.
 * 8. **Never** call `history.replaceState` / `history.pushState` from production page
 *    code — the repo `pageRouterPatternGuard` forbids it; always go through React Router.
 *
 * ## History mode rules (encode in the schema)
 *
 * - Filters and tabs → `history: 'replace'` (refine in place; Back should not stack every keystroke).
 * - Object selection (for example `?signal=`) → `history: 'push'` (Back restores prior selection).
 * - When a patch mixes modes, `writeParams` resolves to `push` if any patched key is `push`,
 *   unless the caller overrides with `{ history }`.
 *
 * ## Refresh / share / back verification checklist
 *
 * After wiring a page:
 * - Change filter/tab/selection → hard refresh → same state restored from the URL.
 * - Copy the URL into a new tab/incognito → same state (share works).
 * - For `push` params, browser Back returns to the previous selection/filter step.
 * - Unrelated query keys (for example `keep=yes`) remain intact across writes.
 *
 * This module is pure: it never mutates `window.history` and does not depend on React.
 */

/** Recommended React Router navigation mode for a parameter write. */
export type UrlHistoryMode = 'replace' | 'push';

/**
 * Single typed query parameter definition.
 * `name` is the wire key; the schema object key is the TypeScript field name.
 */
export type UrlParamDef<T> = {
  name: string;
  parse: (raw: string | null) => T;
  /**
   * Serialize a typed value. Return `null` to delete/omit the key
   * (typically when the value equals the page default).
   */
  serialize: (value: T) => string | null;
  default: T;
  history: UrlHistoryMode;
};

/**
 * Page-level schema: each key is a typed field owned by that page.
 * Uses `any` (not `unknown`) so per-field `UrlParamDef<T>` values remain
 * assignable under TypeScript's function parameter contravariance rules.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type UrlStateSchema = Record<string, UrlParamDef<any>>;

/** Infer the typed values object from a schema. */
export type InferUrlState<S extends UrlStateSchema> = {
  [K in keyof S]: S[K] extends UrlParamDef<infer T> ? T : never;
};

/** Partial patch; `null` resets a field to its schema default (and usually omits the key). */
export type UrlStatePatch<S extends UrlStateSchema> = {
  [K in keyof S]?: InferUrlState<S>[K] | null;
};

export type WriteParamsOptions = {
  /** Current search string or params. Defaults to `window.location.search` when available. */
  search?: string | URLSearchParams;
  /** Force history mode; when omitted, resolved from patched parameter definitions. */
  history?: UrlHistoryMode;
  /**
   * When true (default), query keys not declared in the schema are preserved.
   * Set false only for hard canonicalization that drops foreign keys.
   */
  preserveUnknown?: boolean;
};

export type WriteParamsResult<S extends UrlStateSchema> = {
  /** Search string with leading `?` when non-empty, otherwise `''`. */
  search: string;
  params: URLSearchParams;
  history: UrlHistoryMode;
  values: InferUrlState<S>;
};

function toSearchParams(search: string | URLSearchParams): URLSearchParams {
  if (typeof search !== 'string') {
    return new URLSearchParams(search);
  }
  return new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
}

function defaultSearch(): string {
  if (typeof window === 'undefined') return '';
  return window.location.search;
}

/** Format params as a location.search value (`?a=1` or `''`). */
export function formatSearch(params: URLSearchParams): string {
  const value = params.toString();
  return value ? `?${value}` : '';
}

/**
 * Read and type-convert every schema field from a search string.
 * Missing or invalid values fall back to each field's `default`.
 */
export function readParams<S extends UrlStateSchema>(
  schema: S,
  search: string | URLSearchParams = defaultSearch(),
): InferUrlState<S> {
  const source = toSearchParams(search);
  const values = {} as InferUrlState<S>;
  (Object.keys(schema) as Array<keyof S>).forEach((key) => {
    const def = schema[key];
    values[key] = def.parse(source.get(def.name)) as InferUrlState<S>[typeof key];
  });
  return values;
}

/**
 * Apply a partial patch onto the current search params.
 *
 * - Only keys present in `patch` are rewritten.
 * - Unknown (non-schema) keys are preserved by default.
 * - Unpatched schema keys keep their existing raw query values.
 * - Does not call `history.replaceState` / `pushState`; callers must navigate via React Router.
 */
export function writeParams<S extends UrlStateSchema>(
  schema: S,
  patch: UrlStatePatch<S>,
  options: WriteParamsOptions = {},
): WriteParamsResult<S> {
  const preserveUnknown = options.preserveUnknown !== false;
  const source = toSearchParams(options.search ?? defaultSearch());
  const schemaNames = new Set(
    (Object.keys(schema) as Array<keyof S>).map((key) => schema[key].name),
  );

  const next = new URLSearchParams();
  if (preserveUnknown) {
    source.forEach((value, key) => {
      if (!schemaNames.has(key)) {
        next.append(key, value);
      }
    });
  }

  // Carry unpatched schema keys as currently present (raw), then apply patch.
  (Object.keys(schema) as Array<keyof S>).forEach((key) => {
    const def = schema[key];
    if (Object.prototype.hasOwnProperty.call(patch, key)) {
      return;
    }
    source.getAll(def.name).forEach((value) => {
      next.append(def.name, value);
    });
  });

  const patchedKeys: Array<keyof S> = [];
  (Object.keys(patch) as Array<keyof S>).forEach((key) => {
    if (!Object.prototype.hasOwnProperty.call(schema, key)) return;
    patchedKeys.push(key);
    const def = schema[key];
    // Drop previous values for this owned key before rewriting.
    next.delete(def.name);
    const rawPatch = patch[key];
    const value = (rawPatch === null || rawPatch === undefined
      ? def.default
      : rawPatch) as InferUrlState<S>[typeof key];
    const serialized = def.serialize(value);
    if (serialized !== null) {
      next.set(def.name, serialized);
    }
  });

  const history = options.history ?? resolveHistoryMode(schema, patchedKeys);
  const values = readParams(schema, next);
  return {
    search: formatSearch(next),
    params: next,
    history,
    values,
  };
}

/**
 * Resolve history mode from the schema definitions of the keys being written.
 * Any `push` key in the patch forces `push`; otherwise `replace`.
 */
export function resolveHistoryMode<S extends UrlStateSchema>(
  schema: S,
  patchedKeys: ReadonlyArray<keyof S>,
): UrlHistoryMode {
  for (const key of patchedKeys) {
    const def = schema[key];
    if (def?.history === 'push') return 'push';
  }
  return 'replace';
}

// ---------------------------------------------------------------------------
// Parameter factories (common codecs)
// ---------------------------------------------------------------------------

export type StringParamOptions = {
  name: string;
  default?: string;
  history?: UrlHistoryMode;
  /** When true (default), empty string serializes to omit. */
  omitEmpty?: boolean;
};

export function stringParam(options: StringParamOptions): UrlParamDef<string> {
  const defaultValue = options.default ?? '';
  const omitEmpty = options.omitEmpty !== false;
  return {
    name: options.name,
    default: defaultValue,
    history: options.history ?? 'replace',
    parse: (raw) => {
      if (raw === null) return defaultValue;
      return raw;
    },
    serialize: (value) => {
      if (value === defaultValue) return null;
      if (omitEmpty && value === '') return null;
      return value;
    },
  };
}

export type OptionalStringParamOptions = {
  name: string;
  history?: UrlHistoryMode;
};

/** Nullable string; missing/empty → null; null serializes to omit. */
export function optionalStringParam(
  options: OptionalStringParamOptions,
): UrlParamDef<string | null> {
  return {
    name: options.name,
    default: null,
    history: options.history ?? 'replace',
    parse: (raw) => {
      if (raw === null) return null;
      const trimmed = raw.trim();
      return trimmed === '' ? null : trimmed;
    },
    serialize: (value) => {
      if (value === null || value === undefined) return null;
      const trimmed = value.trim();
      return trimmed === '' ? null : trimmed;
    },
  };
}

export type NumberParamOptions = {
  name: string;
  default?: number | null;
  history?: UrlHistoryMode;
  /** When set, values outside (min, max] fall back to default. */
  min?: number;
  max?: number;
  /** Require integer values (default true). */
  integer?: boolean;
};

/**
 * Integer/number query param. Invalid or out-of-range values fall back to `default`.
 * Serializes `null` and the default value as omitted keys.
 */
export function numberParam(options: NumberParamOptions): UrlParamDef<number | null> {
  const defaultValue = options.default === undefined ? null : options.default;
  const integer = options.integer !== false;
  const min = options.min;
  const max = options.max;

  const isValid = (value: number): boolean => {
    if (!Number.isFinite(value)) return false;
    if (integer && !Number.isInteger(value)) return false;
    if (min !== undefined && value < min) return false;
    if (max !== undefined && value > max) return false;
    return true;
  };

  return {
    name: options.name,
    default: defaultValue,
    history: options.history ?? 'replace',
    parse: (raw) => {
      if (raw === null || raw.trim() === '') return defaultValue;
      const parsed = Number(raw);
      if (!isValid(parsed)) return defaultValue;
      return parsed;
    },
    serialize: (value) => {
      if (value === null || value === undefined) return null;
      if (!isValid(value)) return null;
      if (value === defaultValue) return null;
      return String(value);
    },
  };
}

export type EnumParamOptions<T extends string> = {
  name: string;
  values: readonly T[];
  default: T;
  history?: UrlHistoryMode;
  /** When true, serializing the default omits the key (default true). */
  omitDefault?: boolean;
};

export function enumParam<T extends string>(
  options: EnumParamOptions<T>,
): UrlParamDef<T> {
  const allowed = new Set<string>(options.values);
  const omitDefault = options.omitDefault !== false;
  return {
    name: options.name,
    default: options.default,
    history: options.history ?? 'replace',
    parse: (raw) => {
      if (raw === null) return options.default;
      return allowed.has(raw) ? (raw as T) : options.default;
    },
    serialize: (value) => {
      if (!allowed.has(value)) return null;
      if (omitDefault && value === options.default) return null;
      return value;
    },
  };
}

export type BooleanParamOptions = {
  name: string;
  default?: boolean;
  history?: UrlHistoryMode;
  /** Wire value for true (default `'1'`). */
  trueValue?: string;
};

/** Boolean flag: present trueValue → true; absent/other → default. Default false omits key. */
export function booleanParam(options: BooleanParamOptions): UrlParamDef<boolean> {
  const defaultValue = options.default ?? false;
  const trueValue = options.trueValue ?? '1';
  return {
    name: options.name,
    default: defaultValue,
    history: options.history ?? 'replace',
    parse: (raw) => {
      if (raw === null) return defaultValue;
      return raw === trueValue;
    },
    serialize: (value) => {
      if (value === defaultValue) return null;
      return value ? trueValue : null;
    },
  };
}

/**
 * Define a schema with full type inference for field values.
 * Prefer this over a bare object when exporting page schemas.
 */
export function defineUrlStateSchema<S extends UrlStateSchema>(schema: S): S {
  return schema;
}
