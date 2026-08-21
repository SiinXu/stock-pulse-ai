// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { tmpdir } from 'node:os';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { spawnSync } from 'node:child_process';
import { afterEach, describe, expect, it } from 'vitest';

const TEST_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(TEST_DIRECTORY, '../../..');
const APP_SOURCE_PATH = path.join(WEB_ROOT, 'src/App.tsx');
const CHECKER_PATH = path.join(WEB_ROOT, 'scripts/check-bundle-size.mjs');
const BUDGET_PATH = path.join(WEB_ROOT, 'scripts/bundle-size-budget.json');
const DEFAULT_JS_MAX_GZIP_BYTES = 13436;
const DEFAULT_CSS_MAX_GZIP_BYTES = 28791;
const ROUTE_HEADROOM_BYTES = 400;

type BundleRule = {
  id?: string;
  match?: string | string[];
  maxGzipBytes?: number;
  measuredGzipBytes?: number;
};

type BundleBudget = {
  defaults?: { jsMaxGzipBytes?: number; cssMaxGzipBytes?: number };
  rules?: BundleRule[];
  aggregateRules?: BundleRule[];
};

const temporaryRoots: string[] = [];

afterEach(() => {
  for (const root of temporaryRoots.splice(0)) {
    rmSync(root, { recursive: true, force: true });
  }
});

function createOutput(): string {
  const root = mkdtempSync(path.join(tmpdir(), 'playground-boundary-'));
  temporaryRoots.push(root);
  mkdirSync(path.join(root, 'assets'));
  return root;
}

function writeBudget(root: string): string {
  const budgetPath = path.join(root, 'budget.json');
  writeFileSync(budgetPath, JSON.stringify({
    version: 1,
    outDir: root,
    gzipLevel: 9,
    defaults: {
      jsMaxGzipBytes: 1_000_000,
      cssMaxGzipBytes: 1_000_000,
    },
    rules: [],
  }));
  return budgetPath;
}

function runChecker(budgetPath: string) {
  return spawnSync(
    // @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
    process.execPath,
    [CHECKER_PATH, '--budget', budgetPath, '--print'],
    { cwd: WEB_ROOT, encoding: 'utf8' },
  );
}

describe('playground production boundary', () => {
  it('loads playground pages only behind the compile-time DEV flag', () => {
    const appSource = readFileSync(APP_SOURCE_PATH, 'utf8');

    expect(appSource).not.toMatch(
      /^const (?:ComponentPlaygroundPage|PlaygroundRenderPage) = lazy\(\(\) => import\('\.\/playground\//m,
    );
    expect(appSource).toMatch(
      /if\s*\(\s*!import\.meta\.env\.DEV\s*\)[\s\S]*import\('\.\/playground\/ComponentPlaygroundPage'\)/,
    );
    expect(appSource).toMatch(
      /if\s*\(\s*!import\.meta\.env\.DEV\s*\)[\s\S]*import\('\.\/playground\/PlaygroundRenderPage'\)/,
    );
    expect(appSource).toContain('...createPlaygroundRoutes()');
  });

  it('fails the production bundle check when a playground channel string leaks', () => {
    const root = createOutput();
    writeFileSync(
      path.join(root, 'assets', 'index-hash.js'),
      "window.parent.postMessage({ channel: 'stockpulse-playground' }, '*');\n",
    );
    const result = runChecker(writeBudget(root));

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('development-only mock adapter');
    expect(result.stderr).toContain('stockpulse-playground');
  });

  it('fails the production bundle check when a named playground chunk is present', () => {
    const root = createOutput();
    writeFileSync(
      path.join(root, 'assets', 'PlaygroundRenderPage-hash.js'),
      "export const catalog = 'ready';\n",
    );
    const result = runChecker(writeBudget(root));

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('playground-only chunks');
    expect(result.stderr).toContain('assets/PlaygroundRenderPage-hash.js');
  });

  it('accepts a production asset with no playground modules or chunk names', () => {
    const root = createOutput();
    writeFileSync(
      path.join(root, 'assets', 'HomePage-hash.js'),
      "export const home = 'shell';\n",
    );
    const result = runChecker(writeBudget(root));

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('bundle-size: OK — 1 assets within budget');
  });

  it('remeasures T18 route chunks at measured + 400 B and does not raise default gzip caps', () => {
    const budget = JSON.parse(readFileSync(BUDGET_PATH, 'utf8')) as BundleBudget;
    const remasuredIds = [
      'SettingsPage',
      'DecisionSignalsPage',
      'ChatPage',
      'HomePage',
      'StockScreeningPage',
      'StockDetailsPage',
    ];

    expect(budget.defaults?.jsMaxGzipBytes).toBe(DEFAULT_JS_MAX_GZIP_BYTES);
    expect(budget.defaults?.cssMaxGzipBytes).toBe(DEFAULT_CSS_MAX_GZIP_BYTES);

    for (const id of remasuredIds) {
      const rule = budget.rules?.find((entry) => entry.id === id);
      const family = budget.aggregateRules?.find((entry) => entry.id === `${id}-family`);
      expect(rule, id).toBeDefined();
      expect(family, `${id}-family`).toBeDefined();
      expect(rule?.measuredGzipBytes).toBeGreaterThan(0);
      expect(rule?.maxGzipBytes).toBe((rule?.measuredGzipBytes ?? 0) + ROUTE_HEADROOM_BYTES);
      expect(family?.maxGzipBytes).toBe(rule?.maxGzipBytes);
      expect(family?.match).toEqual([rule?.match]);
    }

    for (const id of ['settings-route', 'portfolio-route', 'screening-route']) {
      const rule = budget.aggregateRules?.find((entry) => entry.id === id);
      expect(rule, id).toBeDefined();
      expect(rule?.measuredGzipBytes).toBeGreaterThan(0);
      expect(rule?.maxGzipBytes).toBe((rule?.measuredGzipBytes ?? 0) + ROUTE_HEADROOM_BYTES);
    }

    const alreadySplitLocaleFamilies = [
      'locale-ja-family',
      'locale-de-family',
      'locale-ko-family',
      'locale-fr-family',
      'locale-es-family',
      'locale-zh-TW-family',
      'locale-ms-family',
      'locale-id-family',
      'locale-extra-family',
    ];
    for (const id of alreadySplitLocaleFamilies) {
      const rule = budget.aggregateRules?.find((entry) => entry.id === id);
      expect(rule, id).toBeDefined();
      expect(rule?.measuredGzipBytes).toBeGreaterThan(0);
      expect(rule?.maxGzipBytes).toBe((rule?.measuredGzipBytes ?? 0) + ROUTE_HEADROOM_BYTES);
    }

    const ruleIds = (budget.rules ?? []).map((rule) => rule.id);
    const aggregateIds = (budget.aggregateRules ?? []).map((rule) => rule.id);
    expect(ruleIds).not.toContain('PlaygroundRenderPage');
    expect(aggregateIds).not.toContain('PlaygroundRenderPage-family');
  });
});
