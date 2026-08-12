// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Emits a production service worker that precaches only the app shell and
 * hashed static assets. Analysis data, market quotes, and API responses are
 * never stored (Refs #234; offline analysis is #218/#990).
 */
import { createHash } from 'node:crypto'
import { writeFileSync } from 'node:fs'
import path from 'node:path'
import type { Plugin } from 'vite'

const NEVER_PRECACHE_BASENAMES = new Set([
  'stocks.index.json',
  'sw.js',
])

function toUrlPath(fileName: string): string {
  const normalized = fileName.replace(/\\/g, '/')
  return normalized.startsWith('/') ? normalized : `/${normalized}`
}

function buildServiceWorkerSource(precacheUrls: string[], cacheVersion: string): string {
  const precacheLiteral = JSON.stringify(precacheUrls, null, 2)
  const cacheNameLiteral = JSON.stringify(`stockpulse-shell-${cacheVersion}`)
  return `/* StockPulse shell service worker — generated at build time. Do not edit. */
/* Cache boundary: app shell + static assets only. Never cache /api/* or market data. */
const CACHE_NAME = ${cacheNameLiteral};
const PRECACHE_URLS = ${precacheLiteral};

function normalizePathname(pathname) {
  if (!pathname) return '/';
  const withoutQuery = pathname.split('?')[0] || pathname;
  const withoutHash = withoutQuery.split('#')[0] || withoutQuery;
  return withoutHash.startsWith('/') ? withoutHash : '/' + withoutHash;
}

function isNeverCachePath(pathname) {
  const path = normalizePathname(pathname);
  if (path === '/api' || path.startsWith('/api/')) return true;
  if (path === '/health' || path.startsWith('/health/')) return true;
  if (path === '/stocks.index.json' || path.endsWith('/stocks.index.json')) return true;
  if (path === '/docs' || path.startsWith('/docs/')) return true;
  if (path === '/redoc' || path.startsWith('/redoc/')) return true;
  if (path === '/openapi.json') return true;
  if (path === '/sw.js') return true;
  return false;
}

function isShellStaticPath(pathname) {
  const path = normalizePathname(pathname);
  if (path === '/manifest.webmanifest') return true;
  if (path === '/vite.svg') return true;
  if (path === '/favicon.ico') return true;
  if (path.startsWith('/icons/')) return true;
  if (path.startsWith('/assets/')) return true;
  return false;
}

function decideStrategy(request) {
  const method = (request.method || 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') return 'network-only';
  let pathname = '/';
  try {
    pathname = new URL(request.url).pathname;
  } catch {
    return 'network-only';
  }
  if (isNeverCachePath(pathname)) return 'network-only';
  if (request.mode === 'navigate' || request.destination === 'document') {
    return 'network-first-navigation';
  }
  if (isShellStaticPath(pathname)) return 'cache-first-shell';
  return 'network-only';
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith('stockpulse-shell-') && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const strategy = decideStrategy(request);

  if (strategy === 'network-only') {
    event.respondWith(fetch(request));
    return;
  }

  if (strategy === 'cache-first-shell') {
    event.respondWith(
      caches.open(CACHE_NAME).then(async (cache) => {
        const cached = await cache.match(request);
        if (cached) return cached;
        const response = await fetch(request);
        if (response && response.ok) {
          cache.put(request, response.clone());
        }
        return response;
      })
    );
    return;
  }

  // network-first-navigation: prefer live HTML, fall back to cached shell offline.
  event.respondWith(
    fetch(request)
      .then(async (response) => {
        if (response && response.ok) {
          const cache = await caches.open(CACHE_NAME);
          cache.put('/index.html', response.clone());
        }
        return response;
      })
      .catch(async () => {
        const cache = await caches.open(CACHE_NAME);
        return (
          (await cache.match('/index.html'))
          || (await cache.match('/'))
          || Response.error()
        );
      })
  );
});
`
}

export function shellPwaPlugin(): Plugin {
  let outDir = 'dist'

  return {
    name: 'stockpulse-shell-pwa',
    apply: 'build',
    configResolved(config) {
      outDir = config.build.outDir
    },
    writeBundle(_options, bundle) {
      // Precache only the install shell: HTML, entry CSS/JS, icons, manifest.
      // Other hashed /assets/* are still cache-first on first network hit
      // (see decideStrategy), never API or market index data.
      const urls = new Set<string>([
        '/',
        '/index.html',
        '/manifest.webmanifest',
        '/icons/icon-192.png',
        '/icons/icon-512.png',
        '/icons/icon-512-maskable.png',
        '/icons/apple-touch-icon.png',
        '/vite.svg',
      ])

      for (const fileName of Object.keys(bundle)) {
        const normalized = fileName.replace(/\\/g, '/')
        const base = path.posix.basename(normalized)
        if (NEVER_PRECACHE_BASENAMES.has(base)) continue
        if (normalized.endsWith('.map')) continue
        // Entry chunks only (index-*.js / index-*.css); lazy route chunks stay
        // cache-first at runtime when requested.
        if (/^assets\/index-[^/]+\.(js|css)$/.test(normalized)) {
          urls.add(toUrlPath(normalized))
        }
      }

      // Explicitly ensure market autocomplete index is never precached even if
      // Vite copies public/stocks.index.json into the output.
      urls.delete('/stocks.index.json')
      urls.delete('/sw.js')

      const sorted = Array.from(urls).sort()
      const cacheVersion = createHash('sha256')
        .update(sorted.join('\n'))
        .digest('hex')
        .slice(0, 12)

      const swSource = buildServiceWorkerSource(sorted, cacheVersion)
      writeFileSync(path.join(outDir, 'sw.js'), swSource, 'utf-8')
    },
  }
}
