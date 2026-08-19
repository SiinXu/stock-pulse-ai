/**
 * Shared Vitest / Testing Library timeout policy for apps/dsa-web.
 *
 * Coverage instrumentation delays production-source scans and React.lazy
 * chunk resolution. Vitest testTimeout and Testing Library findBy/waitFor
 * are independent; raising one does not extend the other.
 *
 * Detection is split on purpose:
 * - CLI argv is authoritative only in the Vitest main process
 *   (`vitest.config.ts`). Fork workers see `[node, .../vitest/dist/workers/forks.js]`
 *   and never receive `--coverage`.
 * - The main process injects `WEB_VITEST_COVERAGE=1` via `test.env`.
 *   `setupTests` reads that worker-visible flag, not `process.argv`.
 */

export const WEB_UNIT_TEST_TIMEOUT_MS = 5_000;
export const WEB_COVERAGE_TEST_TIMEOUT_MS = 30_000;
export const WEB_UNIT_ASYNC_UTIL_TIMEOUT_MS = 1_000;
/** Budget for lazy chunks under v8 coverage. Below Vitest's 30s testTimeout. */
export const WEB_COVERAGE_ASYNC_UTIL_TIMEOUT_MS = 10_000;

/** Worker-visible flag injected from `vitest.config.ts` when CLI coverage is on. */
export const WEB_VITEST_COVERAGE_FLAG = 'WEB_VITEST_COVERAGE';
export const WEB_VITEST_COVERAGE_FLAG_VALUE = '1';

function defaultArgv(): readonly string[] {
  const proc = (globalThis as { process?: { argv?: string[] } }).process;
  return proc?.argv ?? [];
}

function defaultEnv(): Readonly<Record<string, string | undefined>> {
  const proc = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process;
  return proc?.env ?? {};
}

export function isVitestCoverageCliEnabled(argv: readonly string[] = defaultArgv()): boolean {
  return argv.some((argument) => argument === '--coverage' || argument.startsWith('--coverage.'));
}

export function isVitestCoverageWorkerEnabled(
  env: Readonly<Record<string, string | undefined>> = defaultEnv(),
): boolean {
  return env[WEB_VITEST_COVERAGE_FLAG] === WEB_VITEST_COVERAGE_FLAG_VALUE;
}

export function getWebUnitTestTimeoutMs(argv: readonly string[] = defaultArgv()): number {
  return isVitestCoverageCliEnabled(argv) ? WEB_COVERAGE_TEST_TIMEOUT_MS : WEB_UNIT_TEST_TIMEOUT_MS;
}

export function getWebUnitAsyncUtilTimeoutMs(
  env: Readonly<Record<string, string | undefined>> = defaultEnv(),
): number {
  return isVitestCoverageWorkerEnabled(env)
    ? WEB_COVERAGE_ASYNC_UTIL_TIMEOUT_MS
    : WEB_UNIT_ASYNC_UTIL_TIMEOUT_MS;
}
