#!/usr/bin/env node
/**
 * Soft-gate runtime performance budget checker for apps/dsa-web.
 *
 * Runs Issue #883 contract scenarios via Vitest and compares measured values
 * against scripts/runtime-performance-budget.json.
 *
 * Soft mode (default): WARN on exceedance, exit 0.
 * Strict mode (--strict): exit 1 on exceedance.
 */

import { existsSync, readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';

const SCRIPT_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(SCRIPT_DIRECTORY, '..');
const DEFAULT_BUDGET_PATH = path.join(SCRIPT_DIRECTORY, 'runtime-performance-budget.json');
const MEASUREMENT_TEST = 'src/performance/__tests__/runtimePerformanceContracts.test.tsx';

function fail(message) {
  console.error(`runtime-perf: ${message}`);
  process.exitCode = 1;
}

function parseArgs(argv) {
  const options = { budgetPath: DEFAULT_BUDGET_PATH, strict: false, print: true };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--strict') { options.strict = true; continue; }
    if (argument === '--soft') { options.strict = false; continue; }
    if (argument === '--print') { options.print = true; continue; }
    if (argument === '--budget') {
      const value = argv[index + 1];
      if (!value) throw new Error('--budget requires a path');
      options.budgetPath = path.resolve(value);
      index += 1;
      continue;
    }
    if (argument === '--help' || argument === '-h') {
      console.log('Usage: node scripts/check-runtime-performance.mjs [--soft|--strict] [--budget <path>]');
      process.exit(0);
    }
    throw new Error(`Unknown argument: ${argument}`);
  }
  return options;
}

function loadBudget(budgetPath) {
  if (!existsSync(budgetPath)) throw new Error(`Budget file not found: ${budgetPath}`);
  const budget = JSON.parse(readFileSync(budgetPath, 'utf8'));
  if (!budget || typeof budget !== 'object') throw new Error('Budget file must contain a JSON object');
  if (!Array.isArray(budget.scenarios) || budget.scenarios.length === 0) {
    throw new Error('Budget file must include a non-empty scenarios array');
  }
  for (const scenario of budget.scenarios) {
    if (!scenario || typeof scenario !== 'object') throw new Error('Each scenario must be an object');
    if (typeof scenario.id !== 'string' || !scenario.id.trim()) throw new Error('Each scenario requires a non-empty id');
    if (typeof scenario.budget !== 'number' || !Number.isFinite(scenario.budget)) {
      throw new Error(`Scenario ${scenario.id} requires a numeric budget`);
    }
  }
  return budget;
}

function runMeasurements(reportPath) {
  const vitestEntry = path.join(WEB_ROOT, 'node_modules', 'vitest', 'vitest.mjs');
  if (!existsSync(vitestEntry)) {
    throw new Error('vitest is not installed. Run npm ci in apps/dsa-web first.');
  }
  const result = spawnSync(
    process.execPath,
    [vitestEntry, 'run', MEASUREMENT_TEST, '--reporter=dot'],
    {
      cwd: WEB_ROOT,
      encoding: 'utf8',
      env: { ...process.env, DSA_RUNTIME_PERF_REPORT: reportPath },
    },
  );
  if (result.status !== 0) {
    if (result.stdout) console.error(result.stdout);
    if (result.stderr) console.error(result.stderr);
    throw new Error(`Measurement suite failed (exit ${result.status}).`);
  }
  if (!existsSync(reportPath)) {
    throw new Error(`Measurement report missing at ${reportPath}.`);
  }
  return JSON.parse(readFileSync(reportPath, 'utf8'));
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const budget = loadBudget(options.budgetPath);
  const isStrict = options.strict || budget.modeDefault === 'strict';
  const reportDirectory = path.join(tmpdir(), 'dsa-runtime-perf');
  mkdirSync(reportDirectory, { recursive: true });
  const reportPath = path.join(reportDirectory, `report-${process.pid}.json`);

  let report;
  try {
    report = runMeasurements(reportPath);
  } finally {
    try { rmSync(reportPath, { force: true }); } catch { /* ignore */ }
  }

  const measurements = Array.isArray(report?.measurements) ? report.measurements : [];
  const byId = new Map(measurements.map((entry) => [entry.id, entry]));

  console.log(`runtime-perf: mode=${isStrict ? 'strict' : 'soft'} budget=${options.budgetPath}`);
  console.log(`runtime-perf: scenarios=${budget.scenarios.length}`);

  let exceedances = 0;
  let missing = 0;
  for (const scenario of budget.scenarios) {
    const measured = byId.get(scenario.id);
    if (!measured || typeof measured.value !== 'number') {
      missing += 1;
      console.error(`  [MISSING] ${scenario.id}  expected measurement for metric=${scenario.metric}`);
      continue;
    }
    const ok = measured.value <= scenario.budget;
    const status = ok ? 'OK' : (isStrict ? 'FAIL' : 'WARN');
    if (!ok) exceedances += 1;
    if (options.print || !ok) {
      console.log(
        `  [${status}] ${scenario.id}  measured=${measured.value} ${scenario.unit || ''}  `
        + `budget=${scenario.budget}  metric=${scenario.metric}`,
      );
    }
  }

  if (missing > 0) {
    fail(`${missing} scenario(s) missing measurements. Do not shrink measurement coverage to pass the gate.`);
    return;
  }
  if (exceedances > 0) {
    const message = `${exceedances} scenario(s) exceeded runtime budget`;
    if (isStrict) {
      fail(`${message} (strict mode).`);
      return;
    }
    console.warn(`runtime-perf: WARN — ${message} (soft gate; CI continues).`);
    console.log('runtime-perf: soft gate complete');
    return;
  }
  console.log(`runtime-perf: OK — ${budget.scenarios.length} scenarios within budget`);
}

try {
  main();
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
