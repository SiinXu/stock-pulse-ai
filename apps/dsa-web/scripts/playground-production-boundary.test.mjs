// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { afterEach, describe, expect, it } from 'vitest';
import {
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const WEB_ROOT = process.cwd();
const CHECKER_PATH = path.join(WEB_ROOT, 'scripts', 'check-bundle-size.mjs');
const temporaryRoots = [];

afterEach(() => {
  for (const root of temporaryRoots.splice(0)) {
    rmSync(root, { recursive: true, force: true });
  }
});

function createOutput() {
  const root = mkdtempSync(path.join(tmpdir(), 'playground-boundary-'));
  temporaryRoots.push(root);
  mkdirSync(path.join(root, 'assets'));
  return root;
}

function writeBudget(root) {
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

function runChecker(budgetPath) {
  return spawnSync(
    process.execPath,
    [CHECKER_PATH, '--budget', budgetPath, '--print'],
    { cwd: WEB_ROOT, encoding: 'utf8' },
  );
}

describe('playground production bundle boundary', () => {
  it('fails when a production asset still contains the playground channel', () => {
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

  it('fails when a named playground chunk is present in the production assets', () => {
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
});
