// @vitest-environment node
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { getConfig } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  WEB_COVERAGE_ASYNC_UTIL_TIMEOUT_MS,
  WEB_COVERAGE_TEST_TIMEOUT_MS,
  WEB_UNIT_ASYNC_UTIL_TIMEOUT_MS,
  WEB_UNIT_TEST_TIMEOUT_MS,
  WEB_VITEST_COVERAGE_FLAG,
  WEB_VITEST_COVERAGE_FLAG_VALUE,
  getWebUnitAsyncUtilTimeoutMs,
  getWebUnitTestTimeoutMs,
  isVitestCoverageCliEnabled,
  isVitestCoverageWorkerEnabled,
} from '../src/test-utils/coverageTimeouts';

const webRoot = process.cwd();
const baselinePath = path.join(webRoot, 'scripts', 'web-coverage-baseline.json');
const packagePath = path.join(webRoot, 'package.json');
const vitestConfigPath = path.join(webRoot, 'vitest.config.ts');
const setupTestsPath = path.join(webRoot, 'src', 'setupTests.ts');
const coverageTimeoutsPath = path.join(webRoot, 'src', 'test-utils', 'coverageTimeouts.ts');
const placementTestPath = path.join(
  webRoot,
  'src',
  'components',
  'report',
  '__tests__',
  'AnalysisContextSummary.test.tsx',
);

const ALLOWED_EXCLUDES = [
  'src/types/api.generated.ts',
  'src/dev/**',
  'src/playground/**',
  'src/locales/**',
  'src/i18n/translations/**',
  'src/assets/**',
  'src/**/__tests__/**',
  'src/**/*.test.*',
  'src/**/*.spec.*',
  'src/test-utils/**',
  'src/setupTests.ts',
] as const;

const FORBIDDEN_EXCLUDE_PREFIXES = [
  'src/pages/',
  'src/components/',
  'src/hooks/',
  'src/api/',
  'src/stores/',
  'src/utils/',
] as const;

type CoverageMetric = 'lines' | 'functions' | 'statements' | 'branches';

type CoverageBaseline = {
  version: number;
  provider: string;
  all: boolean;
  reportsDirectory: string;
  reporters: string[];
  measuredCommand: string;
  epsilonPercent: number;
  include: string[];
  exclude: string[];
  excludeReasons: Record<string, string>;
  measured: Record<CoverageMetric, number>;
  thresholds: Record<CoverageMetric, number>;
};

function readJson<T>(filePath: string): T {
  return JSON.parse(readFileSync(filePath, 'utf8')) as T;
}

function floorThreshold(measured: number, epsilon: number): number {
  return Math.max(0, Math.floor(measured - epsilon));
}

describe('web unit coverage gate', () => {
  const baseline = readJson<CoverageBaseline>(baselinePath);
  const packageJson = readJson<{
    scripts: Record<string, string>;
    devDependencies: Record<string, string>;
  }>(packagePath);
  const vitestConfig = readFileSync(vitestConfigPath, 'utf8');
  const setupTests = readFileSync(setupTestsPath, 'utf8');
  const coverageTimeouts = readFileSync(coverageTimeoutsPath, 'utf8');
  const placementTest = readFileSync(placementTestPath, 'utf8');

  it('exposes a single coverage command that reuses the unit suite', () => {
    expect(packageJson.scripts.test).toBe('vitest run');
    expect(packageJson.scripts['test:coverage']).toBe('vitest run --coverage');
    expect(packageJson.devDependencies['@vitest/coverage-v8']).toBe('4.1.0');
    expect(packageJson.devDependencies.vitest).toBe('^4.1.0');
    expect(baseline.measuredCommand).toBe('npm run test:coverage');
  });

  it('uses Vitest v8 coverage with an honest all-files include', () => {
    expect(baseline.provider).toBe('v8');
    expect(baseline.all).toBe(true);
    expect(baseline.reportsDirectory).toBe('./coverage');
    expect(baseline.reporters).toEqual(['text', 'json-summary']);
    expect(baseline.include).toEqual(['src/**/*.{ts,tsx}']);
    expect(vitestConfig).toContain("readFileSync(new URL('./scripts/web-coverage-baseline.json'");
    expect(vitestConfig).toContain('provider: coverageBaseline.provider');
    expect(vitestConfig).toContain('all: coverageBaseline.all');
    expect(vitestConfig).toContain('thresholds: coverageBaseline.thresholds');
    expect(vitestConfig).toContain('reportOnFailure: true');
    expect(vitestConfig).toContain('testTimeout: getWebUnitTestTimeoutMs()');
    expect(vitestConfig).not.toContain('testTimeout: coverageEnabled ? 30_000 : 5_000');
  });

  it('aligns Testing Library async waits with coverage-mode Vitest timeouts', () => {
    expect(isVitestCoverageCliEnabled([])).toBe(false);
    expect(isVitestCoverageCliEnabled(['vitest', 'run'])).toBe(false);
    expect(isVitestCoverageCliEnabled(['vitest', 'run', '--coverage'])).toBe(true);
    expect(isVitestCoverageCliEnabled(['vitest', 'run', '--coverage.reporter=text'])).toBe(true);
    expect(isVitestCoverageWorkerEnabled({})).toBe(false);
    expect(isVitestCoverageWorkerEnabled({ [WEB_VITEST_COVERAGE_FLAG]: '0' })).toBe(false);
    expect(isVitestCoverageWorkerEnabled({
      [WEB_VITEST_COVERAGE_FLAG]: WEB_VITEST_COVERAGE_FLAG_VALUE,
    })).toBe(true);
    expect(getWebUnitTestTimeoutMs([])).toBe(WEB_UNIT_TEST_TIMEOUT_MS);
    expect(getWebUnitTestTimeoutMs(['--coverage'])).toBe(WEB_COVERAGE_TEST_TIMEOUT_MS);
    expect(getWebUnitAsyncUtilTimeoutMs({})).toBe(WEB_UNIT_ASYNC_UTIL_TIMEOUT_MS);
    expect(getWebUnitAsyncUtilTimeoutMs({
      [WEB_VITEST_COVERAGE_FLAG]: WEB_VITEST_COVERAGE_FLAG_VALUE,
    })).toBe(WEB_COVERAGE_ASYNC_UTIL_TIMEOUT_MS);
    expect(WEB_COVERAGE_ASYNC_UTIL_TIMEOUT_MS).toBeGreaterThan(WEB_UNIT_ASYNC_UTIL_TIMEOUT_MS);
    expect(WEB_COVERAGE_ASYNC_UTIL_TIMEOUT_MS).toBeLessThan(WEB_COVERAGE_TEST_TIMEOUT_MS);
    expect(WEB_UNIT_TEST_TIMEOUT_MS).toBe(5_000);
    expect(WEB_COVERAGE_TEST_TIMEOUT_MS).toBe(30_000);
    expect(WEB_UNIT_ASYNC_UTIL_TIMEOUT_MS).toBe(1_000);
    expect(WEB_COVERAGE_ASYNC_UTIL_TIMEOUT_MS).toBe(10_000);
    expect(WEB_VITEST_COVERAGE_FLAG).toBe('WEB_VITEST_COVERAGE');
    expect(WEB_VITEST_COVERAGE_FLAG_VALUE).toBe('1');

    // Main process detects CLI coverage and injects one worker-visible flag.
    expect(vitestConfig).toContain('const coverageEnabled = isVitestCoverageCliEnabled()');
    expect(vitestConfig).toContain('[WEB_VITEST_COVERAGE_FLAG]: coverageEnabled ? WEB_VITEST_COVERAGE_FLAG_VALUE : \'\'');
    expect(coverageTimeouts).toContain('isVitestCoverageWorkerEnabled');
    expect(coverageTimeouts).toMatch(
      /export function getWebUnitAsyncUtilTimeoutMs\([\s\S]*isVitestCoverageWorkerEnabled/,
    );
    expect(coverageTimeouts).toMatch(
      /export function getWebUnitTestTimeoutMs\([\s\S]*isVitestCoverageCliEnabled/,
    );
    expect(setupTests).toContain('configure({ asyncUtilTimeout: getWebUnitAsyncUtilTimeoutMs() })');
    expect(setupTests).not.toContain('process.argv');

    // Fork workers never see `--coverage`. Vitest still serializes
    // config.coverage.enabled into the worker — that is independent of our
    // helper and of process.argv. A real coverage process must therefore
    // expose WEB_VITEST_COVERAGE=1 and apply the 10s RTL budget.
    const workerHasCoverageArgv = process.argv.some(
      (argument) => argument === '--coverage' || argument.startsWith('--coverage.'),
    );
    expect(workerHasCoverageArgv).toBe(false);
    const workerState = (
      globalThis as {
        __vitest_worker__?: { config?: { coverage?: { enabled?: boolean } } };
      }
    ).__vitest_worker__;
    const vitestCoverageEnabled = workerState?.config?.coverage?.enabled === true;
    expect(process.env[WEB_VITEST_COVERAGE_FLAG]).toBe(
      vitestCoverageEnabled ? WEB_VITEST_COVERAGE_FLAG_VALUE : '',
    );
    expect(getConfig().asyncUtilTimeout).toBe(
      vitestCoverageEnabled ? WEB_COVERAGE_ASYNC_UTIL_TIMEOUT_MS : WEB_UNIT_ASYNC_UTIL_TIMEOUT_MS,
    );
    expect(getConfig().asyncUtilTimeout).toBe(vitestCoverageEnabled ? 10_000 : 1_000);
  });

  it('waits for lazy report diagnostics together with news before asserting order', () => {
    expect(placementTest).toContain("expect(screen.getByTestId('run-diagnostics')).toBeInTheDocument()");
    expect(placementTest).toContain('const diagnostics = screen.getByTestId(\'run-diagnostics\')');
    expect(placementTest).not.toMatch(/await screen\.findByTestId\('run-diagnostics'\)/);
    expect(placementTest).toContain('ReportDiagnostics is React.lazy');
  });

  it('keeps exclusions limited to generated, vendor, and non-unit-testable assets', () => {
    expect(baseline.exclude).toEqual([...ALLOWED_EXCLUDES]);
    expect(Object.keys(baseline.excludeReasons).sort()).toEqual([...ALLOWED_EXCLUDES].sort());
    for (const pattern of baseline.exclude) {
      expect(
        FORBIDDEN_EXCLUDE_PREFIXES.some((prefix) => pattern.startsWith(prefix)),
        `${pattern} excludes product runtime source`,
      ).toBe(false);
    }
  });

  it('ratchets integer thresholds one point below the recorded measurement', () => {
    const metrics: CoverageMetric[] = ['lines', 'functions', 'statements', 'branches'];
    expect(baseline.epsilonPercent).toBe(1);
    expect(baseline.version).toBe(1);
    for (const metric of metrics) {
      const measured = baseline.measured[metric];
      const threshold = baseline.thresholds[metric];
      expect(measured).toBeGreaterThan(0);
      expect(Number.isInteger(threshold)).toBe(true);
      expect(threshold).toBe(floorThreshold(measured, baseline.epsilonPercent));
    }
  });
});
