#!/usr/bin/env node
/**
 * Assert production bundle gzip sizes against scripts/bundle-size-budget.json.
 *
 * Usage (from apps/dsa-web after a production build):
 *   node scripts/check-bundle-size.mjs
 *   node scripts/check-bundle-size.mjs --print
 *   node scripts/check-bundle-size.mjs --budget path/to/budget.json
 *
 * Exit codes:
 *   0 — all matching assets are within budget
 *   1 — one or more assets exceed budget, or the build output / budget is invalid
 */

import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const SCRIPT_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(SCRIPT_DIRECTORY, '..');
const DEFAULT_BUDGET_PATH = path.join(SCRIPT_DIRECTORY, 'bundle-size-budget.json');

function fail(message) {
  console.error(`bundle-size: ${message}`);
  process.exitCode = 1;
}

function parseArgs(argv) {
  const options = {
    budgetPath: DEFAULT_BUDGET_PATH,
    print: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--print') {
      options.print = true;
      continue;
    }
    if (argument === '--budget') {
      const value = argv[index + 1];
      if (!value) {
        throw new Error('--budget requires a path');
      }
      options.budgetPath = path.resolve(value);
      index += 1;
      continue;
    }
    if (argument === '--help' || argument === '-h') {
      console.log('Usage: node scripts/check-bundle-size.mjs [--print] [--budget <path>]');
      process.exit(0);
    }
    throw new Error(`Unknown argument: ${argument}`);
  }

  return options;
}

/**
 * Convert a simple glob (only `*` wildcards, no `**`) into a RegExp.
 * Patterns are matched against paths using `/` separators.
 */
function globToRegExp(globPattern) {
  const escaped = globPattern
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*/g, '[^/]*');
  return new RegExp(`^${escaped}$`);
}

function loadBudget(budgetPath) {
  if (!existsSync(budgetPath)) {
    throw new Error(`Budget file not found: ${budgetPath}`);
  }

  const budget = JSON.parse(readFileSync(budgetPath, 'utf8'));
  if (!budget || typeof budget !== 'object') {
    throw new Error('Budget file must contain a JSON object');
  }
  if (!Array.isArray(budget.rules)) {
    throw new Error('Budget file must include a rules array');
  }
  if (!budget.defaults || typeof budget.defaults !== 'object') {
    throw new Error('Budget file must include defaults');
  }
  if (
    typeof budget.defaults.jsMaxGzipBytes !== 'number'
    || typeof budget.defaults.cssMaxGzipBytes !== 'number'
  ) {
    throw new Error('Budget defaults must include jsMaxGzipBytes and cssMaxGzipBytes numbers');
  }

  for (const rule of budget.rules) {
    if (!rule || typeof rule !== 'object') {
      throw new Error('Each budget rule must be an object');
    }
    if (typeof rule.id !== 'string' || !rule.id.trim()) {
      throw new Error('Each budget rule requires a non-empty id');
    }
    if (typeof rule.match !== 'string' || !rule.match.trim()) {
      throw new Error(`Budget rule ${rule.id} requires a match glob`);
    }
    if (typeof rule.maxGzipBytes !== 'number' || !Number.isFinite(rule.maxGzipBytes) || rule.maxGzipBytes < 0) {
      throw new Error(`Budget rule ${rule.id} requires a non-negative maxGzipBytes number`);
    }
  }

  return budget;
}

function listAssetFiles(outDir) {
  const assetsDirectory = path.join(outDir, 'assets');
  if (!existsSync(assetsDirectory)) {
    throw new Error(
      `Build assets directory not found: ${assetsDirectory}. Run \`npm run build\` first.`,
    );
  }

  return readdirSync(assetsDirectory)
    .filter((name) => name.endsWith('.js') || name.endsWith('.css'))
    .map((name) => path.join(assetsDirectory, name))
    .filter((filePath) => statSync(filePath).isFile())
    .sort((left, right) => left.localeCompare(right));
}

function gzipSizeBytes(filePath, gzipLevel) {
  const raw = readFileSync(filePath);
  return gzipSync(raw, { level: gzipLevel }).length;
}

function resolveRule(relativePath, rules) {
  for (const rule of rules) {
    if (globToRegExp(rule.match).test(relativePath)) {
      return rule;
    }
  }
  return null;
}

function formatBytes(bytes) {
  return `${bytes} B (${(bytes / 1024).toFixed(2)} KiB)`;
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const budget = loadBudget(options.budgetPath);
  const outDir = path.resolve(WEB_ROOT, budget.outDir || '../../static');
  const gzipLevel = typeof budget.gzipLevel === 'number' ? budget.gzipLevel : 9;
  const rules = budget.rules;

  const files = listAssetFiles(outDir);
  if (files.length === 0) {
    fail(`No .js/.css assets found under ${path.join(outDir, 'assets')}`);
    return;
  }

  const results = [];
  const ruleHitCounts = new Map(rules.map((rule) => [rule.id, 0]));
  let failures = 0;

  for (const filePath of files) {
    const relativePath = path.relative(outDir, filePath).split(path.sep).join('/');
    const matchedRule = resolveRule(relativePath, rules);
    const isCss = relativePath.endsWith('.css');
    const maxGzipBytes = matchedRule
      ? matchedRule.maxGzipBytes
      : (isCss ? budget.defaults.cssMaxGzipBytes : budget.defaults.jsMaxGzipBytes);
    const ruleId = matchedRule ? matchedRule.id : (isCss ? 'default-css' : 'default-js');
    if (matchedRule) {
      ruleHitCounts.set(matchedRule.id, (ruleHitCounts.get(matchedRule.id) || 0) + 1);
    }

    const gzipBytes = gzipSizeBytes(filePath, gzipLevel);
    const ok = gzipBytes <= maxGzipBytes;
    if (!ok) {
      failures += 1;
    }

    results.push({
      relativePath,
      ruleId,
      gzipBytes,
      maxGzipBytes,
      ok,
    });
  }

  results.sort((left, right) => right.gzipBytes - left.gzipBytes);

  if (options.print || failures > 0) {
    console.log(`bundle-size: checking ${results.length} assets under ${outDir}`);
    console.log(`bundle-size: budget ${options.budgetPath}`);
    console.log('bundle-size: top assets by gzip:');
    for (const result of results.slice(0, 15)) {
      const status = result.ok ? 'OK' : 'FAIL';
      console.log(
        `  [${status}] ${result.relativePath}  gzip=${formatBytes(result.gzipBytes)}  budget=${formatBytes(result.maxGzipBytes)}  rule=${result.ruleId}`,
      );
    }
  }

  // Named rules should match at least one artifact so a renamed chunk cannot
  // silently fall through to the looser default budget.
  const missingRules = [];
  for (const rule of rules) {
    if ((ruleHitCounts.get(rule.id) || 0) === 0) {
      missingRules.push(rule.id);
    }
  }
  if (missingRules.length > 0) {
    fail(
      `Budget rule${missingRules.length === 1 ? '' : 's'} matched no build artifact: ${missingRules.join(', ')}. `
      + 'Update scripts/bundle-size-budget.json if chunk names intentionally changed.',
    );
  }

  if (failures > 0) {
    console.error(`bundle-size: ${failures} asset${failures === 1 ? '' : 's'} exceeded budget:`);
    for (const result of results.filter((entry) => !entry.ok)) {
      console.error(
        `  FAIL ${result.relativePath}  gzip=${formatBytes(result.gzipBytes)}  budget=${formatBytes(result.maxGzipBytes)}  rule=${result.ruleId}`,
      );
    }
    fail('Bundle size budget check failed.');
    return;
  }

  console.log(`bundle-size: OK — ${results.length} assets within budget`);
}

try {
  main();
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  fail(message);
  process.exit(1);
}
