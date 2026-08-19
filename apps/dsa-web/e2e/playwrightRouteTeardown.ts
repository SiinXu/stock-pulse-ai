// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Playwright closes the page/context as soon as the test body returns. Async
 * `page.route` handlers — especially those that `await route.fetch()` — can
 * still be in flight, then throw:
 *   Target page, context or browser has been closed
 *
 * Playwright's documented teardown is `unrouteAll({ behavior: 'ignoreErrors' })`
 * while the page is still open. Call this from the shared `test` fixture so
 * every spec inherits the same lifecycle; do not wrap individual handlers in
 * catch-all try/catch.
 */

export type PlaywrightUnrouteBehavior = 'wait' | 'ignoreErrors' | 'default';

export type PlaywrightRouteSurface = {
  isClosed?: () => boolean;
  unrouteAll: (options?: { behavior?: PlaywrightUnrouteBehavior }) => Promise<void>;
};

const CLOSED_TARGET_RE = /Target page, context or browser has been closed/i;

export function isPlaywrightTargetClosedError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return CLOSED_TARGET_RE.test(message);
}

async function unrouteOpenSurface(owner: PlaywrightRouteSurface): Promise<void> {
  if (owner.isClosed?.()) {
    return;
  }
  try {
    await owner.unrouteAll({ behavior: 'ignoreErrors' });
  } catch (error) {
    if (!isPlaywrightTargetClosedError(error)) {
      throw error;
    }
  }
}

export async function disposePlaywrightRoutes(
  page: PlaywrightRouteSurface,
  context?: PlaywrightRouteSurface,
): Promise<void> {
  await unrouteOpenSurface(page);
  if (context) {
    await unrouteOpenSurface(context);
  }
}
