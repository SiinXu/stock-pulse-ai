import { afterEach, describe, expect, it } from 'vitest';
import {
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const SCRIPT_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const CHECKER_PATH = path.join(SCRIPT_DIRECTORY, 'check-runtime-performance.mjs');
const PRODUCTION_BUDGET_PATH = path.join(SCRIPT_DIRECTORY, 'runtime-performance-budget.json');
const temporaryRoots = [];

afterEach(() => {
  for (const root of temporaryRoots.splice(0)) {
    rmSync(root, { recursive: true, force: true });
  }
});

function createRoot() {
  const root = mkdtempSync(path.join(tmpdir(), 'runtime-perf-check-'));
  temporaryRoots.push(root);
  return root;
}

function productionSurfaces(scenarioOverridesById) {
  const production = JSON.parse(readFileSync(PRODUCTION_BUDGET_PATH, 'utf8'));
  return {
    ...production,
    aggregation: { warmupRuns: 0, measuredRuns: 1, stat: 'median' },
    scenarios: production.scenarios.map((scenario) => ({
      ...scenario,
      ...(scenarioOverridesById[scenario.id] ?? {}),
    })),
  };
}

function writeBudget(root, budget) {
  const budgetPath = path.join(root, 'budget.json');
  writeFileSync(budgetPath, JSON.stringify(budget));
  return budgetPath;
}

function writeReport(root, measurements) {
  const reportPath = path.join(root, 'report.json');
  writeFileSync(reportPath, JSON.stringify({ measuredAt: '2026-08-19T00:00:00.000Z', measurements }));
  return reportPath;
}

function passingMeasurements() {
  return [
    { id: 'data-table-virtualization', value: 17, unit: 'rows' },
    { id: 'history-list-virtualization', value: 8, unit: 'rows' },
    { id: 'signals-list-pagination', value: 20, unit: 'cards' },
    { id: 'screening-results-mounted-rows', value: 150, unit: 'rows' },
    { id: 'settings-field-isolation', value: 0, unit: 'renders' },
    { id: 'sse-progress-batching', value: 3, unit: 'commits' },
    { id: 'chat-markdown-isolation', value: 0, unit: 'remounts' },
    { id: 'home-widget-slots', value: 4, unit: 'slots' },
    { id: 'first-chrome-shell', value: 3, unit: 'landmarks' },
  ];
}

function runChecker(args) {
  return spawnSync(process.execPath, [CHECKER_PATH, ...args], {
    cwd: path.resolve(SCRIPT_DIRECTORY, '..'),
    encoding: 'utf8',
  });
}

describe('runtime performance checker gates (Refs #883)', () => {
  it('fails closed when a blocking structural scenario is one unit over budget', () => {
    const root = createRoot();
    const budgetPath = writeBudget(root, productionSurfaces({}));
    const reportPath = writeReport(root, passingMeasurements().map((entry) => (
      entry.id === 'history-list-virtualization' ? { ...entry, value: 41 } : entry
    )));

    const result = runChecker(['--budget', budgetPath, '--report', reportPath, '--print']);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('[FAIL] history-list-virtualization');
    expect(result.stderr).toContain('measured=41 <= budget=40');
    expect(result.stderr).toContain('blocking scenario(s) exceeded runtime budget');
    expect(result.stdout).toContain('[SKIP] bundle-route-split');
    expect(result.stdout).toContain('[SKIP] desktop-idle-power');
  });

  it('warns and exits 0 when only an observe scenario exceeds its honest budget', () => {
    const root = createRoot();
    const budgetPath = writeBudget(root, productionSurfaces({}));
    const reportPath = writeReport(root, passingMeasurements());

    const result = runChecker(['--budget', budgetPath, '--report', reportPath, '--print']);

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('[WARN] screening-results-mounted-rows');
    expect(result.stdout).toContain('measured=150 <= budget=40');
    expect(result.stderr).toContain('observe scenario(s) exceeded budget');
    expect(result.stdout).toContain('1 observe warnings, 2 skipped/unavailable');
    expect(result.stdout).not.toContain('[FAIL]');
  });

  it('does not treat skip/unavailable as a pass or as an exceedance', () => {
    const root = createRoot();
    const budgetPath = writeBudget(root, productionSurfaces({}));
    const reportPath = writeReport(root, passingMeasurements().filter((entry) => (
      entry.id !== 'bundle-route-split' && entry.id !== 'desktop-idle-power'
    )));

    const result = runChecker(['--budget', budgetPath, '--report', reportPath, '--print']);

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('[SKIP] bundle-route-split');
    expect(result.stdout).toContain('not measurable in Web jsdom CI');
    expect(result.stdout).toContain('2 skipped/unavailable');
    expect(result.stderr).not.toContain('[MISSING] bundle-route-split');
    expect(result.stderr).not.toContain('[MISSING] desktop-idle-power');
  });

  it('fails closed when a skip scenario has no skipReason', () => {
    const root = createRoot();
    const budget = productionSurfaces({
      'desktop-idle-power': { skipReason: '' },
    });
    const budgetPath = writeBudget(root, budget);
    const reportPath = writeReport(root, passingMeasurements());

    const result = runChecker(['--budget', budgetPath, '--report', reportPath]);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('desktop-idle-power is skip but missing skipReason');
  });

  it('fails closed when a blocking scenario is missing from the report', () => {
    const root = createRoot();
    const budgetPath = writeBudget(root, productionSurfaces({}));
    const reportPath = writeReport(
      root,
      passingMeasurements().filter((entry) => entry.id !== 'settings-field-isolation'),
    );

    const result = runChecker(['--budget', budgetPath, '--report', reportPath]);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('[MISSING] settings-field-isolation');
    expect(result.stderr).toContain('Do not shrink measurement coverage');
  });

  it('rejects a timing scenario marked blocking so laptop milliseconds cannot become a gate', () => {
    const root = createRoot();
    const budget = productionSurfaces({
      'first-chrome-shell': {
        kind: 'timing',
        gate: 'blocking',
        metric: 'route_switch_ms',
        unit: 'ms',
        budget: 12,
      },
    });
    const budgetPath = writeBudget(root, budget);
    const reportPath = writeReport(root, passingMeasurements());

    const result = runChecker(['--budget', budgetPath, '--report', reportPath]);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('first-chrome-shell cannot be blocking');
    expect(result.stderr).toContain('kind=timing');
  });

  it('rejects a network scenario marked blocking', () => {
    const root = createRoot();
    const budget = productionSurfaces({
      'sse-progress-batching': {
        kind: 'network',
        gate: 'blocking',
        metric: 'ttfb_ms',
        unit: 'ms',
        budget: 50,
      },
    });
    const budgetPath = writeBudget(root, budget);
    const reportPath = writeReport(root, passingMeasurements());

    const result = runChecker(['--budget', budgetPath, '--report', reportPath]);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('sse-progress-batching cannot be blocking');
    expect(result.stderr).toContain('kind=network');
  });

  it('uses median after warmup so one slow sample cannot hide a regression or encode one machine', () => {
    const root = createRoot();
    const budgetPath = writeBudget(root, productionSurfaces({}));
    const reportPath = writeReport(root, passingMeasurements().map((entry) => (
      entry.id === 'history-list-virtualization'
        ? { ...entry, samples: [40, 41, 41, 41], value: 40 }
        : entry
    )));

    const result = runChecker([
      '--budget', budgetPath,
      '--report', reportPath,
      '--warmup', '1',
      '--print',
    ]);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('measured=41 <= budget=40');
    expect(result.stderr).toContain('samples=[41,41,41]');
  });

  it('lets --strict promote an observe exceedance to a blocking failure for promotion rehearsal', () => {
    const root = createRoot();
    const budgetPath = writeBudget(root, productionSurfaces({}));
    const reportPath = writeReport(root, passingMeasurements());

    const result = runChecker(['--budget', budgetPath, '--report', reportPath, '--strict']);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('[FAIL] screening-results-mounted-rows');
    expect(result.stdout).toContain('[SKIP] desktop-idle-power');
  });

  it('lets --soft demote blocking exceedances to warnings without skipping unavailable surfaces', () => {
    const root = createRoot();
    const budgetPath = writeBudget(root, productionSurfaces({}));
    const reportPath = writeReport(root, passingMeasurements().map((entry) => (
      entry.id === 'history-list-virtualization' ? { ...entry, value: 41 } : entry
    )));

    const result = runChecker(['--budget', budgetPath, '--report', reportPath, '--soft', '--print']);

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('[WARN] history-list-virtualization');
    expect(result.stdout).toContain('[SKIP] bundle-route-split');
  });

  it('fails closed when the audited surface catalog is not eleven entries', () => {
    const root = createRoot();
    const budget = productionSurfaces({});
    budget.surfaces = budget.surfaces.slice(0, 10);
    const budgetPath = writeBudget(root, budget);
    const reportPath = writeReport(root, passingMeasurements());

    const result = runChecker(['--budget', budgetPath, '--report', reportPath]);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('must list exactly 11 audited surfaces');
  });
});
