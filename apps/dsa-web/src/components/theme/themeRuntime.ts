// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import {
  DEFAULT_PRICE_DIRECTION_ID,
  DEFAULT_THEME_PACK_ID,
  resolveThemePack,
} from '../../design/themePacks';
import {
  isPriceDirectionId,
  isThemePackId,
  THEME_DOCUMENT_ATTRS,
  THEME_STORAGE_KEYS,
  type PriceDirectionId,
  type ThemePackId,
} from '../../design/theme';

function getDocumentRoot(): HTMLElement | null {
  if (typeof document === 'undefined') return null;
  return document.documentElement;
}

function readStorage(key: string): string | null {
  try {
    if (typeof localStorage === 'undefined') return null;
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    if (typeof localStorage === 'undefined') return;
    localStorage.setItem(key, value);
  } catch {
    // ignore
  }
}

export function readStoredThemePack(): ThemePackId {
  const raw = readStorage(THEME_STORAGE_KEYS.pack);
  return isThemePackId(raw) ? raw : DEFAULT_THEME_PACK_ID;
}

export function readStoredPriceDirection(): PriceDirectionId {
  const raw = readStorage(THEME_STORAGE_KEYS.priceDirection);
  return isPriceDirectionId(raw) ? raw : DEFAULT_PRICE_DIRECTION_ID;
}

export function applyThemePack(packId: ThemePackId, options?: { persist?: boolean }): ThemePackId {
  const resolved = resolveThemePack(packId).id;
  const rootEl = getDocumentRoot();
  if (rootEl) rootEl.setAttribute(THEME_DOCUMENT_ATTRS.pack, resolved);
  if (options?.persist !== false) writeStorage(THEME_STORAGE_KEYS.pack, resolved);
  return resolved;
}

export function applyPriceDirection(
  direction: PriceDirectionId,
  options?: { persist?: boolean },
): PriceDirectionId {
  const resolved: PriceDirectionId = isPriceDirectionId(direction)
    ? direction
    : DEFAULT_PRICE_DIRECTION_ID;
  const rootEl = getDocumentRoot();
  if (rootEl) rootEl.setAttribute(THEME_DOCUMENT_ATTRS.priceDirection, resolved);
  if (options?.persist !== false) writeStorage(THEME_STORAGE_KEYS.priceDirection, resolved);
  return resolved;
}

export function bootstrapThemeAppearance(options?: {
  pack?: ThemePackId | null;
  priceDirection?: PriceDirectionId | null;
  persist?: boolean;
}): { pack: ThemePackId; priceDirection: PriceDirectionId } {
  const pack = applyThemePack(
    isThemePackId(options?.pack) ? options.pack : readStoredThemePack(),
    { persist: options?.persist },
  );
  const priceDirection = applyPriceDirection(
    isPriceDirectionId(options?.priceDirection)
      ? options.priceDirection
      : readStoredPriceDirection(),
    { persist: options?.persist },
  );
  return { pack, priceDirection };
}

export function readDocumentThemePack(): ThemePackId {
  const attr = getDocumentRoot()?.getAttribute(THEME_DOCUMENT_ATTRS.pack);
  return isThemePackId(attr) ? attr : readStoredThemePack();
}

export function readDocumentPriceDirection(): PriceDirectionId {
  const attr = getDocumentRoot()?.getAttribute(THEME_DOCUMENT_ATTRS.priceDirection);
  return isPriceDirectionId(attr) ? attr : readStoredPriceDirection();
}
