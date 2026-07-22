// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
//
// Temporary dev-only API mock switch. Lets the main app be tuned against
// deterministic, larger-scale data without a live backend. Enable via URL
// `?mock=ready|empty|error|slow` (bare `?mock` == ready), which is remembered in
// localStorage; `?mock=off` clears it. `VITE_MOCK_API` acts as a default when no
// URL/localStorage preference is set. This module is imported only from the
// import.meta.env.DEV branch in main.tsx, so it is tree-shaken from production.
import type { PlaygroundFixtureProfile } from '../../playground/types';

const STORAGE_KEY = 'dsa-web:api-mock';
const PROFILES: readonly PlaygroundFixtureProfile[] = ['ready', 'empty', 'error', 'slow'];

function normalizeProfile(raw: string | null | undefined): PlaygroundFixtureProfile | null {
  if (raw == null) return null;
  const value = raw.trim().toLowerCase();
  if (value === '0' || value === 'off' || value === 'false') return null;
  if (value === '' || value === '1' || value === 'on' || value === 'true') return 'ready';
  return PROFILES.includes(value as PlaygroundFixtureProfile)
    ? (value as PlaygroundFixtureProfile)
    : 'ready';
}

// Resolution order: URL `?mock` (persisted) → localStorage → `VITE_MOCK_API`.
function resolveMockProfile(): PlaygroundFixtureProfile | null {
  const params = new URLSearchParams(window.location.search);
  if (params.has('mock')) {
    const fromUrl = normalizeProfile(params.get('mock'));
    if (fromUrl) window.localStorage.setItem(STORAGE_KEY, fromUrl);
    else window.localStorage.removeItem(STORAGE_KEY);
    return fromUrl;
  }
  const fromStorage = normalizeProfile(window.localStorage.getItem(STORAGE_KEY));
  if (fromStorage) return fromStorage;
  return normalizeProfile(import.meta.env.VITE_MOCK_API);
}

export async function installApiMockIfEnabled(): Promise<void> {
  const profile = resolveMockProfile();
  if (!profile) return;
  const { installAppApiMock } = await import('./installAppApiMock');
  installAppApiMock(profile);
  document.documentElement.dataset.apiMock = profile;
  console.info(
    `[dsa-web] API mock ON (profile="${profile}"). ` +
      'Switch with ?mock=ready|empty|error|slow, disable with ?mock=off. ' +
      'Endpoints without a registered fixture return HTTP 501.',
  );
}
