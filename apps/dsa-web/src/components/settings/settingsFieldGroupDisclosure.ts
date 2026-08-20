// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiTextKey } from '../../i18n/uiText';

export type FieldGroupDescriptor = {
  id: string;
  titleKey: UiTextKey;
};

/** Group ids that start expanded on generic Settings field lists. */
export const SETTINGS_DEFAULT_OPEN_GROUP_IDS = ['quote', 'primary', 'schedule'] as const;

export type SettingsDefaultOpenGroupId = (typeof SETTINGS_DEFAULT_OPEN_GROUP_IDS)[number];

/** Deep-link query key targeting a single Settings field (`?field=KEY`). */
export const SETTINGS_FIELD_QUERY_KEY = 'field';

const DEFAULT_OPEN_GROUP_ID_SET = new Set<string>(SETTINGS_DEFAULT_OPEN_GROUP_IDS);

export function isSettingsGroupDefaultOpen(groupId: string): boolean {
  return DEFAULT_OPEN_GROUP_ID_SET.has(groupId);
}

/**
 * Destination views such as Web & Logs filter to groups that are never in the
 * default-open set. Opening those rendered groups after the lazy chunk mounts
 * keeps the view's controls reachable without changing quote/primary/schedule
 * progressive disclosure on lists that still have a primary group.
 */
export function settingsRenderedGroupsNeedDestinationOpen(
  renderedGroupIds: readonly string[],
): boolean {
  return renderedGroupIds.length > 0
    && !renderedGroupIds.some((groupId) => isSettingsGroupDefaultOpen(groupId));
}

export function parseSettingsFieldHash(hash: string): string | null {
  if (!hash.startsWith('#setting-')) {
    return null;
  }
  const key = hash.slice('#setting-'.length).trim();
  return key.length > 0 ? key : null;
}

export function settingsRevealUrlFingerprint(
  queryField?: string | null,
  hash?: string | null,
): string {
  return `${queryField?.trim() ?? ''}|${hash ?? ''}`;
}

export function resolveSettingsRevealFieldKey(options: {
  requestKey?: string | null;
  requestUrlFingerprint?: string | null;
  queryField?: string | null;
  hash?: string | null;
}): string | undefined {
  const fromRequest = options.requestKey?.trim();
  const currentFingerprint = settingsRevealUrlFingerprint(options.queryField, options.hash);
  const requestStillApplies = Boolean(fromRequest)
    && (
      options.requestUrlFingerprint == null
      || options.requestUrlFingerprint === currentFingerprint
    );
  if (requestStillApplies) {
    return fromRequest;
  }
  const fromQuery = options.queryField?.trim();
  if (fromQuery) {
    return fromQuery;
  }
  return options.hash ? parseSettingsFieldHash(options.hash) ?? undefined : undefined;
}

export function focusSettingsFieldWhenPresent(
  fieldKey: string,
  options?: { maxFrames?: number; root?: Document },
): () => void {
  const root = options?.root ?? (typeof document === 'undefined' ? null : document);
  const maxFrames = options?.maxFrames ?? 60;
  let cancelled = false;
  let frames = 0;
  let rafId = 0;

  const attempt = () => {
    if (cancelled || !root) {
      return;
    }
    const el = root.getElementById(`setting-${fieldKey}`);
    const blocked = el?.closest('[inert], [hidden]');
    if (el && !blocked) {
      el.focus();
      if (typeof el.scrollIntoView === 'function') {
        el.scrollIntoView({ block: 'center' });
      }
      return;
    }
    if (frames < maxFrames) {
      frames += 1;
      rafId = requestAnimationFrame(attempt);
    }
  };

  rafId = requestAnimationFrame(attempt);
  return () => {
    cancelled = true;
    cancelAnimationFrame(rafId);
  };
}
