#!/usr/bin/env node
/**
 * Runtime performance budget checker for apps/dsa-web (Issue #883 / T26).
 *
 * Runs structural contract scenarios via Vitest and compares measured values
 * against scripts/runtime-performance-budget.json using per-scenario gates:
 *
 *   blocking — exceedance fails (CI hard gate)
 *   observe  — exceedance warns, exit 0
 *   skip     — first-class unavailable result, not a pass
 *
 * Timing and network kinds cannot be blocking. Missing measurements for
 * blocking/observe scenarios fail closed so coverage cannot be dropped.
 *
 * Soft (--soft) / strict (--strict) override gates for local rehearsal only.
 * CI uses the JSON gates with warmup + repeated measured runs.
 */

import { existsSync, readFileSync, mkdirSync, rmSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';

const SCRIPT_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(SCRIPT_DIRECTORY, '..');
const DEFAULT_BUDGET_PATH = path.join(SCRIPT_DIRECTORY, 'runtime-performance-budget.json');
const MEASUREMENT_TESTS = [
  'src/performance/__tests__/runtimePerformanceContracts.test.tsx',
  'src/performance/__tests__/runtimePerformanceChrome.test.tsx',
];
const STRUCTURAL_KIND = 'structural';
const BLOCKING_FORBIDDEN_KINDS = new Set(['timing', 'network', 'external']);
const VALID_GATES = new Set(['blocking', 'observe', 'skip']);
const VALID_KINDS = new Set(['structural', 'timing', 'network', 'external']);
const VALID_DIRECTIONS = new Set(['atMost', 'atLeast']);
const AUDITED_SURFACE_COUNT = 11;

function fail(message) {
  console.error(`runtime-perf: ${message}`);
  process.exitCode = 1;
}

function parseNonNegativeInteger(value, flag) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error(`${flag} requires a non-negative integer`);
  }
  return parsed;
}

function parsePositiveInteger(value, flag) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    throw new Error(`${flag} requires an integer >= 1`);
  }
  return parsed;
}

function parseArgs(argv) {
  const options = {
    budgetPath: DEFAULT_BUDGET_PATH,
    strict: false,
    soft: false,
    print: true,
    reportPath: null,
    warmup: null,
    repeat: null,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--strict') { options.strict = true; continue; }
    if (argument === '--soft') { options.soft = true; continue; }
    if (argument === '--print') { options.print = true; continue; }
    if (argument === '--budget') {
      const value = argv[index + 1];
      if (!value) throw new Error('--budget requires a path');
      options.budgetPath = path.resolve(value);
      index += 1;
      continue;
    }
    if (argument === '--report') {
      const value = argv[index + 1];
      if (!value) throw new Error('--report requires a path');
      options.reportPath = path.resolve(value);
      index += 1;
      continue;
    }
    if (argument === '--warmup') {
      const value = argv[index + 1];
      if (value === undefined) throw new Error('--warmup requires a count');
      options.warmup = parseNonNegativeInteger(value, '--warmup');
      index += 1;
      continue;
    }
    if (argument === '--repeat') {
      const value = argv[index + 1];
      if (value === undefined) throw new Error('--repeat requires a count');
      options.repeat = parsePositiveInteger(value, '--repeat');
      index += 1;
      continue;
    }
    if (argument === '--help' || argument === '-h') {
      console.log(
        'Usage: node scripts/check-runtime-performance.mjs '
        + '[--soft|--strict] [--budget <path>] [--report <path>] '
        + '[--warmup <n>] [--repeat <n>]',
      );
      process.exit(0);
    }
    throw new Error(`Unknown argument: ${argument}`);
  }
  if (options.strict && options.soft) {
    throw new Error('Use only one of --soft or --strict');
  }
  return options;
}

function median(values) {
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return (sorted[middle - 1] + sorted[middle]) / 2;
  }
  return sorted[middle];
}

function aggregateSamples(samples, warmupRuns, stat) {
  if (!Array.isArray(samples) || samples.length === 0) {
    throw new Error('aggregateSamples requires a non-empty samples array');
  }
  if (warmupRuns >= samples.length) {
    throw new Error(
      `warmupRuns=${warmupRuns} leaves no measured samples (n=${samples.length})`,
    );
  }
  const measured = samples.slice(warmupRuns).filter((value) => Number.isFinite(value));
  if (measured.length === 0) {
    throw new Error('No finite measured samples remain after warmup');
  }
  if (stat !== 'median') {
    throw new Error(`Unsupported aggregation stat: ${stat}`);
  }
  return {
    value: median(measured),
    measured,
    discarded: samples.slice(0, warmupRuns),
  };
}

function withinBudget(value, budget, direction) {
  if (direction === 'atLeast') return value >= budget;
  return value <= budget;
}

function effectiveGate(scenario, { strict, soft }) {
  if (scenario.gate === 'skip') return 'skip';
  if (soft) return 'observe';
  if (strict && scenario.gate === 'observe') return 'blocking';
  return scenario.gate;
}

function loadBudget(budgetPath) {
  if (!existsSync(budgetPath)) throw new Error(`Budget file not found: ${budgetPath}`);
  const budget = JSON.parse(readFileSync(budgetPath, 'utf8'));
  if (!budget || typeof budget !== 'object') throw new Error('Budget file must contain a JSON object');
  if (!Array.isArray(budget.scenarios) || budget.scenarios.length === 0) {
    throw new Error('Budget file must include a non-empty scenarios array');
  }
  if (!Array.isArray(budget.surfaces) || budget.surfaces.length !== AUDITED_SURFACE_COUNT) {
    throw new Error(`Budget file must list exactly ${AUDITED_SURFACE_COUNT} audited surfaces`);
  }

  const surfaceIds = new Set();
  for (const surface of budget.surfaces) {
    if (!surface || typeof surface !== 'object') throw new Error('Each surface must be an object');
    if (typeof surface.id !== 'string' || !surface.id.trim()) {
      throw new Error('Each surface requires a non-empty id');
    }
    if (surfaceIds.has(surface.id)) throw new Error(`Duplicate surface id: ${surface.id}`);
    surfaceIds.add(surface.id);
    if (typeof surface.scenarioId !== 'string' || !surface.scenarioId.trim()) {
      throw new Error(`Surface ${surface.id} requires scenarioId`);
    }
  }

  const scenarioIds = new Set();
  for (const scenario of budget.scenarios) {
    if (!scenario || typeof scenario !== 'object') throw new Error('Each scenario must be an object');
    if (typeof scenario.id !== 'string' || !scenario.id.trim()) {
      throw new Error('Each scenario requires a non-empty id');
    }
    if (scenarioIds.has(scenario.id)) throw new Error(`Duplicate scenario id: ${scenario.id}`);
    scenarioIds.add(scenario.id);
    if (typeof scenario.surfaceId !== 'string' || !surfaceIds.has(scenario.surfaceId)) {
      throw new Error(`Scenario ${scenario.id} must reference a listed surfaceId`);
    }
    if (!VALID_KINDS.has(scenario.kind)) {
      throw new Error(`Scenario ${scenario.id} has invalid kind: ${scenario.kind}`);
    }
    if (!VALID_GATES.has(scenario.gate)) {
      throw new Error(`Scenario ${scenario.id} has invalid gate: ${scenario.gate}`);
    }
    const direction = scenario.direction ?? 'atMost';
    if (!VALID_DIRECTIONS.has(direction)) {
      throw new Error(`Scenario ${scenario.id} has invalid direction: ${direction}`);
    }
    scenario.direction = direction;
    if (scenario.gate === 'skip') {
      if (typeof scenario.skipReason !== 'string' || !scenario.skipReason.trim()) {
        throw new Error(`Scenario ${scenario.id} is skip but missing skipReason`);
      }
      continue;
    }
    if (typeof scenario.budget !== 'number' || !Number.isFinite(scenario.budget)) {
      throw new Error(`Scenario ${scenario.id} requires a numeric budget`);
    }
    if (scenario.gate === 'blocking' && scenario.kind !== STRUCTURAL_KIND) {
      throw new Error(
        `Scenario ${scenario.id} cannot be blocking: kind=${scenario.kind} `
        + '(timing/network/external budgets must stay observe or skip)',
      );
    }
    if (scenario.gate === 'blocking' && BLOCKING_FORBIDDEN_KINDS.has(scenario.kind)) {
      throw new Error(`Scenario ${scenario.id} kind=${scenario.kind} cannot be blocking`);
    }
  }

  for (const surface of budget.surfaces) {
    if (!scenarioIds.has(surface.scenarioId)) {
      throw new Error(`Surface ${surface.id} scenarioId ${surface.scenarioId} is not in scenarios`);
    }
  }

  const aggregation = budget.aggregation ?? {};
  const warmupRuns = Number.isInteger(aggregation.warmupRuns) ? aggregation.warmupRuns : 0;
  const measuredRuns = Number.isInteger(aggregation.measuredRuns) ? aggregation.measuredRuns : 1;
  const stat = aggregation.stat ?? 'median';
  if (warmupRuns < 0) throw new Error('aggregation.warmupRuns must be >= 0');
  if (measuredRuns < 1) throw new Error('aggregation.measuredRuns must be >= 1');
  if (stat !== 'median') throw new Error('aggregation.stat must be "median"');
  budget.aggregation = { ...aggregation, warmupRuns, measuredRuns, stat };
  return budget;
}

function runOneMeasurement(reportPath) {
  const vitestEntry = path.join(WEB_ROOT, 'node_modules', 'vitest', 'vitest.mjs');
  if (!existsSync(vitestEntry)) {
    throw new Error('vitest is not installed. Run npm ci in apps/dsa-web first.');
  }
  const result = spawnSync(
    process.execPath,
    [vitestEntry, 'run', ...MEASUREMENT_TESTS, '--reporter=dot', '--maxWorkers=1'],
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

function collectMeasurements({ reportPath, warmupRuns, measuredRuns }) {
  if (reportPath) {
    if (!existsSync(reportPath)) throw new Error(`Measurement report missing at ${reportPath}.`);
    const report = JSON.parse(readFileSync(reportPath, 'utf8'));
    const measurements = Array.isArray(report?.measurements) ? report.measurements : [];
    return measurements.map((entry) => {
      const samples = Array.isArray(entry.samples) && entry.samples.length > 0
        ? entry.samples
        : (typeof entry.value === 'number' ? [entry.value] : []);
      return { ...entry, samples };
    });
  }

  const reportDirectory = path.join(tmpdir(), 'dsa-runtime-perf');
  mkdirSync(reportDirectory, { recursive: true });
  const totalRuns = warmupRuns + measuredRuns;
  const samplesById = new Map();
  const unitById = new Map();
  const runReports = [];
  try {
    for (let run = 0; run < totalRuns; run += 1) {
      const runReportPath = path.join(reportDirectory, `report-${process.pid}-${run}.json`);
      runReports.push(runReportPath);
      const report = runOneMeasurement(runReportPath);
      const measurements = Array.isArray(report?.measurements) ? report.measurements : [];
      for (const entry of measurements) {
        if (typeof entry?.id !== 'string' || typeof entry.value !== 'number') continue;
        const samples = samplesById.get(entry.id) ?? [];
        samples.push(entry.value);
        samplesById.set(entry.id, samples);
        unitById.set(entry.id, entry.unit || '');
      }
    }
  } finally {
    for (const runReportPath of runReports) {
      try { rmSync(runReportPath, { force: true }); } catch { /* ignore */ }
    }
  }

  return [...samplesById.entries()].map(([id, samples]) => ({
    id,
    unit: unitById.get(id) || '',
    samples,
    value: samples[samples.length - 1],
  }));
}

function evaluate(budget, measurements, { strict, soft, warmupRuns }) {
  const byId = new Map(measurements.map((entry) => [entry.id, entry]));
  const rows = [];
  let blockingFailures = 0;
  let observeExceedances = 0;
  let missing = 0;
  let skipped = 0;
  let schemaFailures = 0;

  for (const scenario of budget.scenarios) {
    const gate = effectiveGate(scenario, { strict, soft });
    if (gate === 'skip') {
      skipped += 1;
      rows.push({
        id: scenario.id,
        status: 'SKIP',
        gate,
        kind: scenario.kind,
        detail: scenario.skipReason,
      });
      continue;
    }

    const measured = byId.get(scenario.id);
    const samples = Array.isArray(measured?.samples) && measured.samples.length > 0
      ? measured.samples
      : (typeof measured?.value === 'number' ? [measured.value] : []);
    if (samples.length === 0) {
      missing += 1;
      rows.push({
        id: scenario.id,
        status: 'MISSING',
        gate,
        kind: scenario.kind,
        detail: `expected measurement for metric=${scenario.metric}`,
      });
      continue;
    }

    let aggregated;
    try {
      aggregated = aggregateSamples(samples, warmupRuns, budget.aggregation.stat);
    } catch (error) {
      schemaFailures += 1;
      rows.push({
        id: scenario.id,
        status: 'FAIL',
        gate,
        kind: scenario.kind,
        detail: error instanceof Error ? error.message : String(error),
      });
      continue;
    }

    const ok = withinBudget(aggregated.value, scenario.budget, scenario.direction);
    if (!ok && gate === 'blocking') blockingFailures += 1;
    if (!ok && gate === 'observe') observeExceedances += 1;
    const status = ok ? 'OK' : (gate === 'blocking' ? 'FAIL' : 'WARN');
    const comparator = scenario.direction === 'atLeast' ? '>=' : '<=';
    rows.push({
      id: scenario.id,
      status,
      gate,
      kind: scenario.kind,
      value: aggregated.value,
      budget: scenario.budget,
      unit: scenario.unit || measured?.unit || '',
      metric: scenario.metric,
      samples: aggregated.measured,
      discarded: aggregated.discarded,
      detail: `measured=${aggregated.value} ${comparator} budget=${scenario.budget}`,
    });
  }

  return {
    rows,
    blockingFailures,
    observeExceedances,
    missing,
    skipped,
    schemaFailures,
  };
}

function printRows(rows, { print }) {
  for (const row of rows) {
    if (!print && (row.status === 'OK' || row.status === 'SKIP')) continue;
    if (row.status === 'SKIP') {
      console.log(`  [SKIP] ${row.id}  kind=${row.kind}  ${row.detail}`);
      continue;
    }
    if (row.status === 'MISSING') {
      console.error(`  [MISSING] ${row.id}  ${row.detail}`);
      continue;
    }
    const stream = row.status === 'FAIL' ? console.error : console.log;
    const sampleNote = Array.isArray(row.samples)
      ? `  samples=[${row.samples.join(',')}]`
      : '';
    stream(
      `  [${row.status}] ${row.id}  ${row.detail}`
      + (row.unit ? ` ${row.unit}` : '')
      + `  gate=${row.gate}  metric=${row.metric || row.kind}`
      + sampleNote,
    );
  }
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const budget = loadBudget(options.budgetPath);
  const warmupRuns = options.warmup ?? budget.aggregation.warmupRuns;
  const measuredRuns = options.repeat ?? budget.aggregation.measuredRuns;
  const usingFixture = Boolean(options.reportPath);
  const measurements = collectMeasurements({
    reportPath: options.reportPath,
    warmupRuns: usingFixture ? 0 : warmupRuns,
    measuredRuns: usingFixture ? 1 : measuredRuns,
  });
  const evaluationWarmup = options.warmup ?? (usingFixture ? 0 : warmupRuns);
  const result = evaluate(budget, measurements, {
    strict: options.strict,
    soft: options.soft,
    warmupRuns: evaluationWarmup,
  });

  const mode = options.soft ? 'soft-override' : (options.strict ? 'strict-override' : 'per-scenario');
  console.log(`runtime-perf: mode=${mode} budget=${options.budgetPath}`);
  console.log(
    `runtime-perf: surfaces=${budget.surfaces.length} scenarios=${budget.scenarios.length} `
    + `warmup=${usingFixture ? 0 : warmupRuns} measuredRuns=${usingFixture ? 'fixture' : measuredRuns} `
    + `stat=${budget.aggregation.stat}`,
  );
  printRows(result.rows, { print: options.print });

  if (result.schemaFailures > 0) {
    fail(`${result.schemaFailures} scenario(s) failed aggregation.`);
    return;
  }
  if (result.missing > 0) {
    fail(`${result.missing} scenario(s) missing measurements. Do not shrink measurement coverage to pass the gate.`);
    return;
  }
  if (result.blockingFailures > 0) {
    fail(`${result.blockingFailures} blocking scenario(s) exceeded runtime budget.`);
    return;
  }
  if (result.observeExceedances > 0) {
    console.warn(
      `runtime-perf: WARN — ${result.observeExceedances} observe scenario(s) exceeded budget `
      + '(non-blocking; do not raise the cap to hide this).',
    );
  }
  const blockingCount = budget.scenarios.filter((scenario) => effectiveGate(scenario, options) === 'blocking').length;
  console.log(
    `runtime-perf: OK — ${blockingCount} blocking within budget, `
    + `${result.observeExceedances} observe warnings, ${result.skipped} skipped/unavailable`,
  );
}

try {
  main();
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
