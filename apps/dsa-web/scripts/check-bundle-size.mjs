#!/usr/bin/env node
/**
 * Assert production bundle gzip sizes against scripts/bundle-size-budget.json.
 *
 * Per-asset rules keep each matching file under its own cap. Optional
 * aggregateRules sum every unique asset that matches a family of globs so
 * splitting one route or component into many smaller chunks cannot hide
 * growth behind the per-file budgets (Refs #883).
 *
 * A family with source "indexHtmlModulepreload" (id "criticalPath") ignores
 * its match globs and instead sums the type="module" entry script plus every
 * rel="modulepreload" href in the built index.html. Renaming a split sibling
 * therefore still counts against the family.
 *
 * Usage (from apps/dsa-web after a production build):
 *   node scripts/check-bundle-size.mjs
 *   node scripts/check-bundle-size.mjs --print
 *   node scripts/check-bundle-size.mjs --budget path/to/budget.json
 *
 * Exit codes:
 *   0 — all matching assets and aggregate families are within budget
 *   1 — one or more assets or families exceed budget, or the build output / budget is invalid
 */

import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const SCRIPT_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(SCRIPT_DIRECTORY, '..');
const DEFAULT_BUDGET_PATH = path.join(SCRIPT_DIRECTORY, 'bundle-size-budget.json');

// Production runtime must not resolve playground modules or the mock adapter (Refs #883).
const FORBIDDEN_PRODUCTION_SUBSTRINGS = Object.freeze([
  'axios-mock-adapter',
  'playground_mock_not_registered',
  'stockpulse-playground',
]);
const FORBIDDEN_PRODUCTION_ASSET_GLOBS = Object.freeze([
  'assets/PlaygroundRenderPage-*.js',
  'assets/ComponentPlaygroundPage-*.js',
]);
const ISOLATED_SETTINGS_HELP_FORBIDDEN_GLOBS = Object.freeze([
  'assets/SettingsPage-*.js',
  'assets/settings-*.js',
  'assets/settingsPage-*.js',
  'assets/settingsTranslations-*.js',
  'assets/extra-locale-*.js',
  'assets/ja-*.js',
  'assets/de-*.js',
  'assets/ko-*.js',
  'assets/fr-*.js',
  'assets/es-*.js',
  'assets/id-*.js',
  'assets/ms-*.js',
  'assets/zh-TW-*.js',
]);
const ISOLATED_SETTINGS_HELP_PAYLOADS = Object.freeze([
  {
    id: 'skill-retrieval',
    label: 'Skill retrieval help',
    marker: 'How many catalog skills automatic SkillRouter may retrieve by description',
    allowedGlob: 'assets/CredentialInput-*.js',
  },
  {
    id: 'red-team',
    label: 'Red-team help',
    marker: 'Run one tool-free post-Decision red-team review on Native Multi full/specialist analysis.',
    allowedGlob: 'assets/CredentialInput-*.js',
  },
]);
const INDEX_HTML_MODULEPRELOAD_SOURCE = 'indexHtmlModulepreload';
const CRITICAL_PATH_FAMILY_ID = 'criticalPath';

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

function normalizeMatchPatterns(match, label) {
  const values = Array.isArray(match) ? match : [match];
  if (values.length === 0) {
    throw new Error(`${label} requires at least one match glob`);
  }
  const patterns = [];
  for (const value of values) {
    if (typeof value !== 'string' || !value.trim()) {
      throw new Error(`${label} match patterns must be non-empty strings`);
    }
    patterns.push(value.trim());
  }
  return patterns;
}

function assertBudgetRuleShape(rule, label, seenIds) {
  if (!rule || typeof rule !== 'object') {
    throw new Error(`Each ${label} must be an object`);
  }
  if (typeof rule.id !== 'string' || !rule.id.trim()) {
    throw new Error(`Each ${label} requires a non-empty id`);
  }
  if (seenIds.has(rule.id)) {
    throw new Error(`Duplicate ${label} id: ${rule.id}`);
  }
  seenIds.add(rule.id);
  if (typeof rule.maxGzipBytes !== 'number' || !Number.isFinite(rule.maxGzipBytes) || rule.maxGzipBytes < 0) {
    throw new Error(`${label} ${rule.id} requires a non-negative maxGzipBytes number`);
  }
}

function normalizeAggregateSource(rule) {
  if (rule.id === CRITICAL_PATH_FAMILY_ID && rule.source !== INDEX_HTML_MODULEPRELOAD_SOURCE) {
    throw new Error(
      `Aggregate rule ${CRITICAL_PATH_FAMILY_ID} requires source "${INDEX_HTML_MODULEPRELOAD_SOURCE}"`,
    );
  }
  if (rule.source === undefined) {
    return undefined;
  }
  if (rule.source !== INDEX_HTML_MODULEPRELOAD_SOURCE) {
    throw new Error(`Aggregate rule ${rule.id} has unknown source: ${rule.source}`);
  }
  return rule.source;
}

function getQuotedAttr(tag, name) {
  const match = tag.match(new RegExp(`\\b${name}\\s*=\\s*(["'])([^"']*)\\1`, 'i'));
  return match ? match[2] : null;
}

function normalizeAssetHref(href, label) {
  if (typeof href !== 'string' || !href.trim()) {
    throw new Error(`${label} href is empty`);
  }
  let value = href.trim();
  const hashIndex = value.indexOf('#');
  if (hashIndex >= 0) {
    value = value.slice(0, hashIndex);
  }
  const queryIndex = value.indexOf('?');
  if (queryIndex >= 0) {
    value = value.slice(0, queryIndex);
  }
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(value)) {
    try {
      value = new URL(value).pathname;
    } catch {
      throw new Error(`${label} href is not a build asset: ${href}`);
    }
  }
  value = value.replace(/\\/g, '/');
  while (value.startsWith('./')) {
    value = value.slice(2);
  }
  value = value.replace(/^\/+/, '');
  if (!value.startsWith('assets/') || value.split('/').includes('..')) {
    throw new Error(`${label} href is not a build asset: ${href}`);
  }
  if (!(value.endsWith('.js') || value.endsWith('.css'))) {
    throw new Error(`${label} href is not a js/css asset: ${href}`);
  }
  return value;
}

function collectIndexHtmlCriticalPath(outDir) {
  const indexPath = path.join(outDir, 'index.html');
  if (!existsSync(indexPath)) {
    throw new Error(
      `index.html not found under ${outDir}. Run \`npm run build\` first.`,
    );
  }

  const html = readFileSync(indexPath, 'utf8');
  const matched = [];
  const seen = new Set();
  let hasEntry = false;

  const add = (href, label) => {
    const relativePath = normalizeAssetHref(href, label);
    if (seen.has(relativePath)) {
      return;
    }
    seen.add(relativePath);
    matched.push(relativePath);
  };

  for (const tag of html.match(/<script\b[^>]*>/gi) || []) {
    const type = (getQuotedAttr(tag, 'type') || '').toLowerCase();
    if (type !== 'module') {
      continue;
    }
    const src = getQuotedAttr(tag, 'src');
    if (!src) {
      continue;
    }
    add(src, 'criticalPath entry script');
    hasEntry = true;
  }

  if (!hasEntry) {
    throw new Error('index.html has no type="module" entry script with src');
  }

  for (const tag of html.match(/<link\b[^>]*>/gi) || []) {
    const rel = (getQuotedAttr(tag, 'rel') || '').toLowerCase();
    if (rel !== 'modulepreload') {
      continue;
    }
    const href = getQuotedAttr(tag, 'href');
    if (!href) {
      throw new Error('criticalPath modulepreload link is missing href');
    }
    add(href, 'criticalPath modulepreload');
  }

  return matched;
}

function gzipBytesForMatchedPaths(ruleId, matchedPaths, gzipByRelativePath) {
  return matchedPaths.reduce((total, relativePath) => {
    const size = gzipByRelativePath.get(relativePath);
    if (typeof size !== 'number') {
      throw new Error(`Aggregate rule ${ruleId} has no gzip size for ${relativePath}`);
    }
    return total + size;
  }, 0);
}

function resolveAggregateMatchedPaths(rule, relativePaths, gzipByRelativePath, outDir) {
  if (rule.source === INDEX_HTML_MODULEPRELOAD_SOURCE) {
    const matchedPaths = collectIndexHtmlCriticalPath(outDir);
    const missing = matchedPaths.filter((relativePath) => !gzipByRelativePath.has(relativePath));
    if (missing.length > 0) {
      throw new Error(
        `Aggregate rule ${rule.id} references missing build artifacts: ${missing.join(', ')}.`,
      );
    }
    return matchedPaths;
  }
  return matchRelativePaths(relativePaths, rule.match);
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
  if (budget.aggregateRules !== undefined && !Array.isArray(budget.aggregateRules)) {
    throw new Error('Budget aggregateRules must be an array when present');
  }

  const ruleIds = new Set();
  for (const rule of budget.rules) {
    assertBudgetRuleShape(rule, 'budget rule', ruleIds);
    if (typeof rule.match !== 'string' || !rule.match.trim()) {
      throw new Error(`Budget rule ${rule.id} requires a match glob`);
    }
  }

  const aggregateIds = new Set();
  const aggregateRules = [];
  for (const rule of budget.aggregateRules || []) {
    assertBudgetRuleShape(rule, 'aggregate rule', aggregateIds);
    const source = normalizeAggregateSource(rule);
    aggregateRules.push({
      ...rule,
      source,
      match: normalizeMatchPatterns(rule.match, `Aggregate rule ${rule.id}`),
    });
  }

  return { ...budget, aggregateRules };
}

function matchRelativePaths(relativePaths, patterns) {
  const matched = [];
  const seen = new Set();
  for (const relativePath of relativePaths) {
    for (const pattern of patterns) {
      if (!globToRegExp(pattern).test(relativePath)) {
        continue;
      }
      if (!seen.has(relativePath)) {
        seen.add(relativePath);
        matched.push(relativePath);
      }
      break;
    }
  }
  return matched;
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

  const forbiddenFindings = [];
  for (const filePath of files) {
    if (!filePath.endsWith('.js')) continue;
    const contents = readFileSync(filePath, 'utf8');
    const relativePath = path.relative(outDir, filePath).split(path.sep).join('/');
    for (const needle of FORBIDDEN_PRODUCTION_SUBSTRINGS) {
      if (contents.includes(needle)) {
        forbiddenFindings.push({ relativePath, needle });
      }
    }
  }
  if (forbiddenFindings.length > 0) {
    fail('Production bundle contains development-only mock adapter code:');
    for (const finding of forbiddenFindings) {
      fail(`  ${finding.relativePath} contains ${finding.needle}`);
    }
    return;
  }

  const forbiddenAssets = [];
  for (const filePath of files) {
    const relativePath = path.relative(outDir, filePath).split(path.sep).join('/');
    for (const pattern of FORBIDDEN_PRODUCTION_ASSET_GLOBS) {
      if (globToRegExp(pattern).test(relativePath)) {
        forbiddenAssets.push({ relativePath, pattern });
      }
    }
  }
  if (forbiddenAssets.length > 0) {
    fail('Production bundle includes playground-only chunks:');
    for (const finding of forbiddenAssets) {
      fail(`  ${finding.relativePath} matches ${finding.pattern}`);
    }
    return;
  }

  const isolatedHelpHits = new Map(ISOLATED_SETTINGS_HELP_PAYLOADS.map((payload) => [payload.id, []]));
  let hasSettingsOrCredentialChunk = false;
  for (const filePath of files) {
    if (!filePath.endsWith('.js')) continue;
    const relativePath = path.relative(outDir, filePath).split(path.sep).join('/');
    if (
      globToRegExp('assets/SettingsPage-*.js').test(relativePath)
      || ISOLATED_SETTINGS_HELP_PAYLOADS.some((payload) => globToRegExp(payload.allowedGlob).test(relativePath))
    ) {
      hasSettingsOrCredentialChunk = true;
    }
    const contents = readFileSync(filePath, 'utf8');
    for (const payload of ISOLATED_SETTINGS_HELP_PAYLOADS) {
      if (contents.includes(payload.marker)) {
        isolatedHelpHits.get(payload.id).push(relativePath);
      }
    }
  }
  for (const payload of ISOLATED_SETTINGS_HELP_PAYLOADS) {
    const hits = isolatedHelpHits.get(payload.id) || [];
    if (hits.length === 0) {
      if (hasSettingsOrCredentialChunk) {
        fail(
          `${payload.label} marker missing from production chunks; expected ${payload.allowedGlob}`,
        );
        return;
      }
      continue;
    }
    const leaked = hits.filter((relativePath) => (
      ISOLATED_SETTINGS_HELP_FORBIDDEN_GLOBS.some((pattern) => globToRegExp(pattern).test(relativePath))
    ));
    const allowedHits = hits.filter((relativePath) => (
      globToRegExp(payload.allowedGlob).test(relativePath)
    ));
    if (leaked.length > 0) {
      fail(`${payload.label} leaked into Settings/locale families: ${leaked.join(', ')}`);
      return;
    }
    if (allowedHits.length === 0) {
      fail(
        `${payload.label} must live on ${payload.allowedGlob}, found: ${hits.join(', ')}`,
      );
      return;
    }
  }

  const results = [];
  const gzipByRelativePath = new Map();
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
    gzipByRelativePath.set(relativePath, gzipBytes);
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
  const relativePaths = results.map((result) => result.relativePath);

  const aggregateResults = [];
  for (const rule of budget.aggregateRules) {
    const matchedPaths = resolveAggregateMatchedPaths(
      rule,
      relativePaths,
      gzipByRelativePath,
      outDir,
    );
    const gzipBytes = gzipBytesForMatchedPaths(rule.id, matchedPaths, gzipByRelativePath);
    const ok = matchedPaths.length > 0 && gzipBytes <= rule.maxGzipBytes;
    if (matchedPaths.length > 0 && gzipBytes > rule.maxGzipBytes) {
      failures += 1;
    }
    aggregateResults.push({
      id: rule.id,
      match: rule.match,
      matchedPaths,
      gzipBytes,
      maxGzipBytes: rule.maxGzipBytes,
      ok,
    });
  }

  const shouldPrint = options.print || failures > 0 || aggregateResults.some((entry) => !entry.ok);
  if (shouldPrint) {
    console.log(`bundle-size: checking ${results.length} assets under ${outDir}`);
    console.log(`bundle-size: budget ${options.budgetPath}`);
    console.log('bundle-size: top assets by gzip:');
    for (const result of results.slice(0, 15)) {
      const status = result.ok ? 'OK' : 'FAIL';
      console.log(
        `  [${status}] ${result.relativePath}  gzip=${formatBytes(result.gzipBytes)}  budget=${formatBytes(result.maxGzipBytes)}  rule=${result.ruleId}`,
      );
    }
    if (aggregateResults.length > 0) {
      console.log('bundle-size: aggregate families:');
      for (const result of aggregateResults) {
        const status = result.ok ? 'OK' : 'FAIL';
        console.log(
          `  [${status}] ${result.id}  gzip=${formatBytes(result.gzipBytes)}  budget=${formatBytes(result.maxGzipBytes)}  assets=${result.matchedPaths.length}`,
        );
        for (const relativePath of result.matchedPaths) {
          console.log(
            `    ${relativePath}  gzip=${formatBytes(gzipByRelativePath.get(relativePath))}`,
          );
        }
      }
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

  const missingAggregates = aggregateResults.filter((entry) => entry.matchedPaths.length === 0);
  if (missingAggregates.length > 0) {
    fail(
      `Aggregate rule${missingAggregates.length === 1 ? '' : 's'} matched no build artifact: ${missingAggregates.map((entry) => entry.id).join(', ')}. `
      + 'Update scripts/bundle-size-budget.json if chunk names intentionally changed.',
    );
  }

  if (failures > 0) {
    const failedAssets = results.filter((entry) => !entry.ok);
    const failedAggregates = aggregateResults.filter((entry) => entry.matchedPaths.length > 0 && !entry.ok);
    if (failedAssets.length > 0) {
      console.error(`bundle-size: ${failedAssets.length} asset${failedAssets.length === 1 ? '' : 's'} exceeded budget:`);
      for (const result of failedAssets) {
        console.error(
          `  FAIL ${result.relativePath}  gzip=${formatBytes(result.gzipBytes)}  budget=${formatBytes(result.maxGzipBytes)}  rule=${result.ruleId}`,
        );
      }
    }
    if (failedAggregates.length > 0) {
      console.error(`bundle-size: ${failedAggregates.length} aggregate famil${failedAggregates.length === 1 ? 'y' : 'ies'} exceeded budget:`);
      for (const result of failedAggregates) {
        console.error(
          `  FAIL ${result.id}  gzip=${formatBytes(result.gzipBytes)}  budget=${formatBytes(result.maxGzipBytes)}  assets=${result.matchedPaths.join(', ')}`,
        );
      }
    }
    fail('Bundle size budget check failed.');
    return;
  }

  const aggregateSuffix = aggregateResults.length > 0
    ? `, ${aggregateResults.length} aggregate famil${aggregateResults.length === 1 ? 'y' : 'ies'}`
    : '';
  console.log(`bundle-size: OK — ${results.length} assets${aggregateSuffix} within budget`);
}

try {
  main();
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  fail(message);
  process.exit(1);
}
