/**
 * Shared Vitest / Testing Library timeout policy for apps/dsa-web.
 *
 * Coverage instrumentation delays production-source scans and React.lazy
 * chunk resolution. Vitest testTimeout and Testing Library findBy/waitFor
 * are independent; raising one does not extend the other.
 */

export const WEB_UNIT_TEST_TIMEOUT_MS = 5_000;
export const WEB_COVERAGE_TEST_TIMEOUT_MS = 30_000;
export const WEB_UNIT_ASYNC_UTIL_TIMEOUT_MS = 1_000;
/** Budget for lazy chunks under v8 coverage. Below Vitest's 30s testTimeout. */
export const WEB_COVERAGE_ASYNC_UTIL_TIMEOUT_MS = 10_000;

function defaultArgv(): readonly string[] {
  const proc = (globalThis as { process?: { argv?: string[] } }).process;
  return proc?.argv ?? [];
}

export function isVitestCoverageEnabled(argv: readonly string[] = defaultArgv()): boolean {
  return argv.some((argument) => argument === '--coverage' || argument.startsWith('--coverage.'));
}

export function getWebUnitTestTimeoutMs(argv: readonly string[] = defaultArgv()): number {
  return isVitestCoverageEnabled(argv) ? WEB_COVERAGE_TEST_TIMEOUT_MS : WEB_UNIT_TEST_TIMEOUT_MS;
}

export function getWebUnitAsyncUtilTimeoutMs(argv: readonly string[] = defaultArgv()): number {
  return isVitestCoverageEnabled(argv)
    ? WEB_COVERAGE_ASYNC_UTIL_TIMEOUT_MS
    : WEB_UNIT_ASYNC_UTIL_TIMEOUT_MS;
}
