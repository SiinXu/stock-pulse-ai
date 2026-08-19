// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { readFileSync } from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const TEST_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(TEST_DIRECTORY, '../../..');
const APP_SOURCE_PATH = path.join(WEB_ROOT, 'src/App.tsx');
const CHECKER_PATH = path.join(WEB_ROOT, 'scripts/check-bundle-size.mjs');
const BUDGET_PATH = path.join(WEB_ROOT, 'scripts/bundle-size-budget.json');

type BundleBudget = {
  rules?: Array<{ id?: string; match?: string }>;
  aggregateRules?: Array<{ id?: string; match?: string | string[] }>;
};

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

  it('does not keep a named production budget for playground chunks', () => {
    const budget = JSON.parse(readFileSync(BUDGET_PATH, 'utf8')) as BundleBudget;
    const ruleIds = (budget.rules ?? []).map((rule) => rule.id);
    const aggregateIds = (budget.aggregateRules ?? []).map((rule) => rule.id);
    const matches = [
      ...(budget.rules ?? []).map((rule) => rule.match),
      ...(budget.aggregateRules ?? []).flatMap((rule) => (
        Array.isArray(rule.match) ? rule.match : [rule.match]
      )),
    ];

    expect(ruleIds).not.toContain('PlaygroundRenderPage');
    expect(aggregateIds).not.toContain('PlaygroundRenderPage-family');
    expect(matches.some((value) => value?.includes('Playground'))).toBe(false);
  });

  it('pins production bundle checks against playground modules and chunks', () => {
    const checkerSource = readFileSync(CHECKER_PATH, 'utf8');

    expect(checkerSource).toContain("'stockpulse-playground'");
    expect(checkerSource).toContain("'playground_mock_not_registered'");
    expect(checkerSource).toContain("'axios-mock-adapter'");
    expect(checkerSource).toContain("'assets/PlaygroundRenderPage-*.js'");
    expect(checkerSource).toContain("'assets/ComponentPlaygroundPage-*.js'");
    expect(checkerSource).toContain('Production bundle includes playground-only chunks');
  });
});
