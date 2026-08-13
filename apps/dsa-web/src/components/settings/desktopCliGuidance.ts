// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { getDesktopRuntimeApi } from './desktopUpdateModel';

export type DesktopCliCommandGuidance = {
  name: string;
  status: 'available' | 'missing' | 'unknown';
  reason: string | null;
  statusLabel: string;
  hint: string;
  installGuideAvailable: boolean;
};

export type DesktopCliGuidancePayload = {
  schemaVersion?: number;
  generatedAt?: string | null;
  platform?: string;
  path?: {
    effectiveEntryCount?: number;
    limited?: boolean;
    augmented?: boolean;
    policy?: string;
  };
  copy?: {
    title?: string;
    intro?: string;
    openTerminal?: string;
    openInstallGuide?: string;
    recheck?: string;
    pathUnavailable?: string | null;
  };
  needsAction?: boolean;
  commands?: DesktopCliCommandGuidance[];
};

export function isDesktopCliGuidanceApiAvailable() {
  const api = getDesktopRuntimeApi() as
    | (ReturnType<typeof getDesktopRuntimeApi> & {
      getEnvDiagnostics?: (payload?: { locale?: string }) => Promise<DesktopCliGuidancePayload>;
      openOperatorTerminal?: (payload?: { locale?: string }) => Promise<{ ok?: boolean; message?: string }>;
      openCliInstallGuide?: (payload?: {
        command?: string;
        locale?: string;
      }) => Promise<{ ok?: boolean; message?: string; urlHost?: string }>;
    })
    | undefined;
  return Boolean(api && typeof api.getEnvDiagnostics === 'function');
}

function containsForbiddenPathToken(value: string) {
  return /\/opt\/homebrew|\/usr\/local\/bin|\/Users\/|C:\\|C:\/|Application Support|PATHEXT/i.test(value);
}

export function assertDesktopCliGuidancePathSafe(payload: DesktopCliGuidancePayload | null | undefined) {
  if (!payload) {
    return;
  }
  const serialized = JSON.stringify(payload);
  if (containsForbiddenPathToken(serialized)) {
    throw new Error('Desktop CLI guidance payload leaked a filesystem path token');
  }
}
