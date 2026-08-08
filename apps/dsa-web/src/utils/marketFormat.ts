// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Multi-market number / timezone / change-color formatting contract (Issue #889).
 *
 * Module-first delivery: this file defines the shared contract only.
 * Existing pages/components still format independently; wiring is a second wave
 * of small PRs (one surface at a time). Color semantics are high-risk in
 * finance UIs — adopt only after per-call-site human review.
 *
 * Rule sources (do not invent):
 * - Currency code display: docs/financial-terminology-guide.md §11 (`currencyDisplay: 'code'`).
 * - Market IANA timezones: src/core/trading_calendar.py `MARKET_TIMEZONE`.
 * - Change color preference values: backend `MARKET_REVIEW_COLOR_SCHEME`
 *   (`green_up` / `red_up`) in src/core/config_registry_parts/system.py.
 * - Market default color convention: backend share_image `_stock_positive_tone`
 *   treats CN/HK symbols as red-up; US/international as green-up.
 * - A-share display precision 2dp: SSE/SZSE quotation unit 0.01 CNY; backend
 *   limit-up/limit-down math rounds to two decimals.
 * - HK display precision 3dp: multi-market UI display default; HKEX tick size
 *   varies by price band (not a single tick). Consumers needing band-aware
 *   ticks must pass an override once that API exists.
 * - US display precision 2dp: standard equity quote display; sub-dollar names
 *   may quote finer but the contract default is 2.
 * - Trading calendar: not implemented here — see `TRADING_CALENDAR_DEPENDENCY`.
 */

import type { UiLanguage } from '../i18n/uiText';
import { formatUiNumber, getUiLocale } from './uiLocale';

/** Primary multi-market IDs covered by this contract (Issue #889). */
export type MarketId = 'cn' | 'hk' | 'us';

/**
 * User/config color preference for up/down presentation.
 * Values match `MARKET_REVIEW_COLOR_SCHEME` (Settings system group).
 * This module accepts the preference; it does not own Settings UI.
 */
export type ChangeColorPreference = 'red_up' | 'green_up';

/** Direction of a signed change value. */
export type ChangeDirection = 'up' | 'down' | 'flat';

/**
 * Resolved paint token after applying direction + color preference.
 * Consumers map `red`/`green`/`neutral` to theme classes (e.g. danger/success).
 * Never present direction by color alone — also show sign/text.
 */
export type ChangeColor = 'red' | 'green' | 'neutral';

export type ChangeSemantics = {
  direction: ChangeDirection;
  /** Preference actually applied (userPref if set, else market default). */
  colorPreference: ChangeColorPreference;
  color: ChangeColor;
};

export type MarketTimeParts = {
  /** Human-readable as-of string including an explicit timezone label. */
  text: string;
  /** IANA timezone used for formatting. */
  timeZone: string;
  /** Short label such as `GMT+8` or `EST` / `EDT` / `GMT-4`. */
  timeZoneLabel: string;
  /** Instant as ISO-8601 in UTC when the input parsed successfully. */
  iso: string;
};

/** ISO 4217 quote currency by market. */
export const MARKET_CURRENCY: Readonly<Record<MarketId, string>> = {
  cn: 'CNY',
  hk: 'HKD',
  us: 'USD',
};

/**
 * Default fraction digits for equity price display by market.
 * See module JSDoc for exchange / backend evidence.
 */
export const MARKET_PRICE_FRACTION_DIGITS: Readonly<Record<MarketId, number>> = {
  cn: 2,
  hk: 3,
  us: 2,
};

/**
 * Mirrors `src/core/trading_calendar.py` `MARKET_TIMEZONE` for cn/hk/us.
 */
export const MARKET_IANA_TIMEZONE: Readonly<Record<MarketId, string>> = {
  cn: 'Asia/Shanghai',
  hk: 'Asia/Hong_Kong',
  us: 'America/New_York',
};

/**
 * Trading-day data is intentionally not resolved in the Web client.
 *
 * Authoritative backend source:
 * - Module: `src/core/trading_calendar.py`
 * - Exchange codes: cn=`XSHG`, hk=`XHKG`, us=`XNYS` (via `exchange-calendars` when installed)
 * - Timezones: `MARKET_IANA_TIMEZONE` above
 * - Existing consumers: scheduled tasks (`calendar_market`, `non_trading_day_policy`),
 *   market phase (`is_trading_day` on phase context)
 *
 * Client code that needs trading-day truth should call a backend API rather than
 * re-implement calendars here.
 */
export const TRADING_CALENDAR_DEPENDENCY = {
  status: 'stub' as const,
  backendModule: 'src/core/trading_calendar.py',
  exchangeCalendars: { cn: 'XSHG', hk: 'XHKG', us: 'XNYS' } as const,
  timeZones: MARKET_IANA_TIMEZONE,
};

const EMPTY_PRICE = '—';

/** CSS design tokens for red/green paint (names follow CN convention; map by color token, not direction). */
export const CHANGE_COLOR_CSS_VAR: Readonly<Record<Exclude<ChangeColor, 'neutral'>, string>> = {
  // --home-price-up is the red hue; --home-price-down is the green hue (DESIGN_GUIDE §2.4).
  red: 'var(--home-price-up)',
  green: 'var(--home-price-down)',
};

function isMarketId(value: string): value is MarketId {
  return value === 'cn' || value === 'hk' || value === 'us';
}

/**
 * Infer cn/hk/us from a stock code for formatting adoption.
 *
 * Mirrors `src/market/context.py` `detect_market` for the three markets this
 * module supports. Returns `null` for empty input, JP/KR/TW suffix symbols, and
 * unrecognized forms — callers must not guess a MarketId.
 */
export function resolveMarketIdFromStockCode(code: string | null | undefined): MarketId | null {
  if (!code || !code.trim()) return null;
  const normalized = code.trim().toUpperCase();

  // HK: HK00700, HK.00700, 00700.HK, or pure 5-digit
  if (/^HK\.?\d{1,5}$/.test(normalized) || normalized.endsWith('.HK')) {
    return 'hk';
  }
  if (/^\d{5}$/.test(normalized)) {
    return 'hk';
  }

  // JP / KR / TW Yahoo suffixes — supported by backend detect_market but not by MarketId.
  if (/\.(?:T|KS|KQ|TW|TWO)$/.test(normalized)) {
    return null;
  }

  // US: 1–5 letters, optional class suffix (AAPL, BRK.B)
  if (/^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$/.test(normalized)) {
    return 'us';
  }

  // A-share 6-digit (with optional SH/SZ/BJ prefix/suffix)
  if (/^\d{6}$/.test(normalized)) {
    return 'cn';
  }
  if (/^(?:SH|SZ|BJ)\d{6}$/.test(normalized)) {
    return 'cn';
  }
  if (/^\d{6}\.(?:SH|SS|SZ|BJ)$/.test(normalized)) {
    return 'cn';
  }

  return null;
}

/**
 * Coerce a raw config/settings string into a known ChangeColorPreference.
 * Unknown or empty values → null (caller uses market convention).
 */
export function parseChangeColorPreference(
  value: string | null | undefined,
): ChangeColorPreference | null {
  if (value === null || value === undefined) return null;
  const normalized = value.trim().toLowerCase().replace(/-/g, '_');
  if (normalized === 'red_up' || normalized === 'green_up') {
    return normalized;
  }
  return null;
}

/**
 * Market convention default for change colors when the user has not set a preference.
 * CN/HK: red-up / green-down. US: green-up / red-down.
 */
export function defaultChangeColorPreference(market: MarketId): ChangeColorPreference {
  return market === 'us' ? 'green_up' : 'red_up';
}

/**
 * Resolve effective color preference: userPref wins when it is a known value;
 * otherwise fall back to market convention.
 */
export function resolveChangeColorPreference(
  market: MarketId,
  userPref?: ChangeColorPreference | null,
): ChangeColorPreference {
  if (userPref === 'red_up' || userPref === 'green_up') {
    return userPref;
  }
  return defaultChangeColorPreference(market);
}

/**
 * Map `changeSemantics(...).color` paint token to a CSS color value.
 * Uses design tokens (red/green hues). Never encode direction by color alone.
 */
export function changeColorCssVar(color: ChangeColor): string | undefined {
  if (color === 'red' || color === 'green') {
    return CHANGE_COLOR_CSS_VAR[color];
  }
  return undefined;
}

/**
 * Signed change percent for display (e.g. `+1.25%`, `-0.50%`). Missing → em dash.
 */
export function formatSignedChangePercent(
  value: number | null | undefined,
  fractionDigits = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return EMPTY_PRICE;
  }
  const numeric = Number(value);
  const sign = numeric > 0 ? '+' : '';
  return `${sign}${numeric.toFixed(fractionDigits)}%`;
}

/**
 * Signed absolute change amount using market price precision (no currency code).
 * Prefer pairing with `formatPrice` for the absolute level and this for the delta.
 */
export function formatSignedChangeAmount(
  value: number | null | undefined,
  market: MarketId,
  language: UiLanguage = 'en',
): string {
  if (!isMarketId(market)) {
    throw new Error(`Unsupported market for formatSignedChangeAmount: ${String(market)}`);
  }
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return EMPTY_PRICE;
  }
  const numeric = Number(value);
  const digits = MARKET_PRICE_FRACTION_DIGITS[market];
  const amount = formatUiNumber(Math.abs(numeric), language, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  if (numeric > 0) return `+${amount}`;
  if (numeric < 0) return `-${amount}`;
  return amount;
}

/**
 * Format an equity price with market currency code, fixed precision, and locale grouping.
 *
 * @param value - Numeric price; null/undefined/NaN → `—`
 * @param market - cn | hk | us
 * @param language - UI language for digit grouping only (currency code stays ISO)
 */
export function formatPrice(
  value: number | null | undefined,
  market: MarketId,
  language: UiLanguage = 'en',
): string {
  if (!isMarketId(market)) {
    throw new Error(`Unsupported market for formatPrice: ${String(market)}`);
  }
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return EMPTY_PRICE;
  }
  const digits = MARKET_PRICE_FRACTION_DIGITS[market];
  const amount = formatUiNumber(Number(value), language, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return `${MARKET_CURRENCY[market]} ${amount}`;
}

/**
 * Classify a signed change and resolve color tokens under preference rules.
 *
 * Preference order: explicit `userPref` → market convention default.
 * Direction is always derived from the numeric sign (not from color).
 */
export function changeSemantics(
  value: number | null | undefined,
  market: MarketId,
  userPref?: ChangeColorPreference | null,
): ChangeSemantics {
  if (!isMarketId(market)) {
    throw new Error(`Unsupported market for changeSemantics: ${String(market)}`);
  }
  const colorPreference = resolveChangeColorPreference(market, userPref);

  let direction: ChangeDirection = 'flat';
  if (value !== null && value !== undefined && !Number.isNaN(Number(value))) {
    const numeric = Number(value);
    if (numeric > 0) direction = 'up';
    else if (numeric < 0) direction = 'down';
  }

  let color: ChangeColor = 'neutral';
  if (direction === 'up') {
    color = colorPreference === 'red_up' ? 'red' : 'green';
  } else if (direction === 'down') {
    color = colorPreference === 'red_up' ? 'green' : 'red';
  }

  return { direction, colorPreference, color };
}

function parseTimestamp(ts: string | number | Date): Date | null {
  const date = ts instanceof Date ? ts : new Date(ts);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

/**
 * Extract a short timezone label for the formatted instant in `timeZone`.
 * Prefers `shortOffset` (e.g. GMT+8); falls back to `short` (e.g. EST).
 */
function resolveTimeZoneLabel(date: Date, timeZone: string, locale: string): string {
  try {
    const offsetParts = new Intl.DateTimeFormat(locale, {
      timeZone,
      timeZoneName: 'shortOffset',
    }).formatToParts(date);
    const offsetName = offsetParts.find((part) => part.type === 'timeZoneName')?.value;
    if (offsetName) return offsetName.replace('UTC', 'GMT');
  } catch {
    // Older runtimes may lack shortOffset; fall through.
  }

  const shortParts = new Intl.DateTimeFormat(locale, {
    timeZone,
    timeZoneName: 'short',
  }).formatToParts(date);
  const shortName = shortParts.find((part) => part.type === 'timeZoneName')?.value;
  if (shortName) return shortName;

  // Stable fallbacks aligned with common market labels (plan: GMT+8 / EST).
  if (timeZone === 'Asia/Shanghai' || timeZone === 'Asia/Hong_Kong') return 'GMT+8';
  if (timeZone === 'America/New_York') return 'EST';
  return timeZone;
}

/**
 * Format a timestamp in the market's trading timezone with an explicit TZ label.
 *
 * @param ts - epoch ms, Date, or parseable string
 * @param market - cn | hk | us
 * @param language - UI language for the date/time digits
 * @returns null when input is missing or unparseable
 */
export function formatMarketTime(
  ts: string | number | Date | null | undefined,
  market: MarketId,
  language: UiLanguage = 'en',
): MarketTimeParts | null {
  if (!isMarketId(market)) {
    throw new Error(`Unsupported market for formatMarketTime: ${String(market)}`);
  }
  if (ts === null || ts === undefined || ts === '') return null;

  const date = parseTimestamp(ts);
  if (!date) return null;

  const timeZone = MARKET_IANA_TIMEZONE[market];
  const locale = getUiLocale(language);
  const timeZoneLabel = resolveTimeZoneLabel(date, timeZone, locale);

  const body = new Intl.DateTimeFormat(locale, {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);

  return {
    text: `${body} ${timeZoneLabel}`,
    timeZone,
    timeZoneLabel,
    iso: date.toISOString(),
  };
}

/**
 * Trading-day stub. Always returns `null` (unknown) until a backend-backed
 * client API is adopted. See `TRADING_CALENDAR_DEPENDENCY`.
 *
 * Parameters are part of the stable contract surface for second-wave adopters.
 *
 * @returns null — unknown; never invents a yes/no answer client-side
 */
export function isTradingDay(market: MarketId, date: string): null {
  void market;
  void date;
  return null;
}
