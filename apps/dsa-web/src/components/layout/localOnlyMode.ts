// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { buildSettingsHref } from '../../routing/routes';

export const LOCAL_ONLY_MODE_FIELD_KEY = 'LOCAL_ONLY_MODE';

/** Settings → Auth & Security, focusing the Local Only Mode field. */
export function buildLocalOnlyModeSettingsHref(): string {
  const href = buildSettingsHref({
    section: 'system_security',
    view: 'security',
  });
  const separator = href.includes('?') ? '&' : '?';
  return `${href}${separator}field=${encodeURIComponent(LOCAL_ONLY_MODE_FIELD_KEY)}`;
}
