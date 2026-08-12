// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Conservative shell-only cache policy for the Web PWA service worker.
 *
 * Boundary (Refs #234): cache only the app shell and static assets.
 * Never cache analysis results, market quotes, stock indexes, or API traffic.
 * Offline analysis / local-first data modes are owned by #218 / #990.
 */

export const SHELL_CACHE_NAME_PREFIX = 'stockpulse-shell-';

export type ShellCacheDecision =
  | 'network-only'
  | 'cache-first-shell'
  | 'network-first-navigation';

function normalizePathname(pathname: string): string {
  if (!pathname) return '/';
  const withoutQuery = pathname.split('?')[0] ?? pathname;
  const withoutHash = withoutQuery.split('#')[0] ?? withoutQuery;
  if (!withoutHash.startsWith('/')) {
    return `/${withoutHash}`;
  }
  return withoutHash;
}

/**
 * Paths that must always hit the network and must never enter the shell cache.
 * Includes API, health, market/autocomplete index, and OpenAPI surfaces.
 */
export function isNeverCachePath(pathname: string): boolean {
  const path = normalizePathname(pathname);

  if (path === '/api' || path.startsWith('/api/')) return true;
  if (path === '/health' || path.startsWith('/health/')) return true;
  if (path === '/stocks.index.json' || path.endsWith('/stocks.index.json')) return true;
  if (path === '/docs' || path.startsWith('/docs/')) return true;
  if (path === '/redoc' || path.startsWith('/redoc/')) return true;
  if (path === '/openapi.json') return true;
  // Never cache the service worker script itself through the SW fetch path.
  if (path === '/sw.js') return true;
  return false;
}

/**
 * Same-origin static shell resources that may use cache-first after install.
 */
export function isShellStaticPath(pathname: string): boolean {
  const path = normalizePathname(pathname);

  if (path === '/manifest.webmanifest') return true;
  if (path === '/vite.svg') return true;
  if (path === '/favicon.ico') return true;
  if (path.startsWith('/icons/')) return true;
  // Vite production assets are content-hashed under /assets/.
  if (path.startsWith('/assets/')) return true;
  return false;
}

export function isNavigationRequest(input: {
  mode?: string;
  destination?: string;
}): boolean {
  return input.mode === 'navigate' || input.destination === 'document';
}

/**
 * Decide how the service worker should handle a request.
 * Non-GET methods are always network-only (no store).
 */
export function decideShellCacheStrategy(input: {
  method: string;
  url: string;
  mode?: string;
  destination?: string;
}): ShellCacheDecision {
  const method = (input.method || 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') {
    return 'network-only';
  }

  let pathname = '/';
  try {
    pathname = new URL(input.url, 'http://local.invalid').pathname;
  } catch {
    return 'network-only';
  }

  if (isNeverCachePath(pathname)) {
    return 'network-only';
  }

  if (isNavigationRequest(input)) {
    return 'network-first-navigation';
  }

  if (isShellStaticPath(pathname)) {
    return 'cache-first-shell';
  }

  // Default deny: unknown same-origin routes stay network-only and uncached.
  return 'network-only';
}
