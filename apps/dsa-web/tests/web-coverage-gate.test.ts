// @vitest-environment node
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const webRoot = process.cwd();
const baselinePath = path.join(webRoot, 'scripts', 'web-coverage-baseline.json');
const packagePath = path.join(webRoot, 'package.json');
const vitestConfigPath = path.join(webRoot, 'vitest.config.ts');

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
    expect(vitestConfig).toContain('testTimeout: coverageEnabled ? 30_000 : 5_000');
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
