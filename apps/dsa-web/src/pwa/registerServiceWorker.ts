// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Production-only service worker registration for the shell PWA.
 * Dev servers skip registration so HMR and proxy behaviour stay unaffected.
 */

export type ServiceWorkerRegistrationLike = {
  scope: string;
};

export type ServiceWorkerContainerLike = {
  register: (
    scriptURL: string,
    options?: { scope?: string; updateViaCache?: 'all' | 'imports' | 'none' },
  ) => Promise<ServiceWorkerRegistrationLike>;
};

export type RegisterServiceWorkerOptions = {
  /** When false, registration is skipped (default: production only). */
  enabled?: boolean;
  /** Injected for tests; defaults to navigator.serviceWorker when present. */
  container?: ServiceWorkerContainerLike | null;
  /** Script URL; defaults to /sw.js at the app origin. */
  scriptUrl?: string;
  /** Registration scope; defaults to /. */
  scope?: string;
  /** Optional logger for non-fatal registration failures. */
  onError?: (error: unknown) => void;
};

export function shouldRegisterServiceWorker(
  options: { enabled?: boolean; hasContainer: boolean } = { hasContainer: false },
): boolean {
  if (options.enabled === false) return false;
  if (options.enabled === true) return options.hasContainer;
  // Default: only when explicitly enabled by the caller (production entry).
  return false;
}

export async function registerServiceWorker(
  options: RegisterServiceWorkerOptions = {},
): Promise<ServiceWorkerRegistrationLike | null> {
  const container =
    options.container
    ?? (typeof navigator !== 'undefined'
      ? (navigator.serviceWorker as ServiceWorkerContainerLike | undefined) ?? null
      : null);

  const enabled =
    options.enabled
    ?? (typeof import.meta !== 'undefined' && Boolean(import.meta.env?.PROD));

  if (!shouldRegisterServiceWorker({
    enabled,
    hasContainer: Boolean(container),
  }) || !container) {
    return null;
  }

  try {
    // updateViaCache: 'none' forces the browser to revalidate sw.js instead of
    // reusing a stale HTTP-cached worker script after deploys.
    return await container.register(options.scriptUrl ?? '/sw.js', {
      scope: options.scope ?? '/',
      updateViaCache: 'none',
    });
  } catch (error) {
    options.onError?.(error);
    return null;
  }
}
