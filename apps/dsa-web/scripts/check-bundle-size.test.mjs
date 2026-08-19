import { afterEach, describe, expect, it } from 'vitest';
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { gzipSync } from 'node:zlib';

const WEB_ROOT = process.cwd();
const CHECKER_PATH = path.join(WEB_ROOT, 'scripts', 'check-bundle-size.mjs');
const temporaryRoots = [];

afterEach(() => {
  for (const root of temporaryRoots.splice(0)) {
    rmSync(root, { recursive: true, force: true });
  }
});

function createOutput({ withAssetsDirectory = true } = {}) {
  const root = mkdtempSync(path.join(tmpdir(), 'bundle-size-check-'));
  temporaryRoots.push(root);
  if (withAssetsDirectory) {
    mkdirSync(path.join(root, 'assets'));
  }
  return root;
}

function writeBudget(root, rules) {
  const budgetPath = path.join(root, 'budget.json');
  writeFileSync(budgetPath, JSON.stringify({
    version: 1,
    outDir: root,
    gzipLevel: 9,
    defaults: {
      jsMaxGzipBytes: 1_000_000,
      cssMaxGzipBytes: 1_000_000,
    },
    rules,
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

describe('bundle size checker', () => {
  const assetName = 'ContractChunk-hash.js';
  const assetContents = Buffer.from("export const contract = 'bundle-size';\n".repeat(64));

  function writeContractAsset(root) {
    writeFileSync(path.join(root, 'assets', assetName), assetContents);
    return gzipSync(assetContents, { level: 9 }).length;
  }

  it('accepts an asset exactly at its gzip cap', () => {
    const root = createOutput();
    const gzipBytes = writeContractAsset(root);
    const budgetPath = writeBudget(root, [{
      id: 'contract',
      match: 'assets/ContractChunk-*.js',
      maxGzipBytes: gzipBytes,
    }]);

    const result = runChecker(budgetPath);

    expect(result.status).toBe(0);
    expect(result.stdout).toContain(`gzip=${gzipBytes} B`);
    expect(result.stdout).toContain('bundle-size: OK — 1 assets within budget');
  });

  it('fails when an asset is one byte above its gzip cap', () => {
    const root = createOutput();
    const gzipBytes = writeContractAsset(root);
    const budgetPath = writeBudget(root, [{
      id: 'contract',
      match: 'assets/ContractChunk-*.js',
      maxGzipBytes: gzipBytes - 1,
    }]);

    const result = runChecker(budgetPath);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain(`FAIL assets/${assetName}`);
    expect(result.stderr).toContain('Bundle size budget check failed.');
  });

  it('fails when a named rule matches no artifact', () => {
    const root = createOutput();
    writeFileSync(path.join(root, 'assets', 'OtherChunk-hash.js'), assetContents);
    const budgetPath = writeBudget(root, [{
      id: 'contract',
      match: 'assets/ContractChunk-*.js',
      maxGzipBytes: 1_000_000,
    }]);

    const result = runChecker(budgetPath);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain(
      'Budget rule matched no build artifact: contract.',
    );
  });

  it('fails when the build assets directory is missing', () => {
    const root = createOutput({ withAssetsDirectory: false });
    const budgetPath = writeBudget(root, []);

    const result = runChecker(budgetPath);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('Build assets directory not found:');
    expect(result.stderr).toContain('Run `npm run build` first.');
  });

  it('fails when a production asset still contains the mock adapter', () => {
    const root = createOutput();
    writeFileSync(
      path.join(root, 'assets', 'index-hash.js'),
      "import AxiosMockAdapter from 'axios-mock-adapter';\n",
    );
    const budgetPath = writeBudget(root, []);

    const result = runChecker(budgetPath);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('development-only mock adapter');
    expect(result.stderr).toContain('axios-mock-adapter');
  });

  it('fails when the build output contains no JavaScript or CSS assets', () => {
    const root = createOutput();
    writeFileSync(path.join(root, 'assets', 'manifest.txt'), 'not a bundle asset');
    const budgetPath = writeBudget(root, []);

    const result = runChecker(budgetPath);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('No .js/.css assets found under');
  });
});

describe('first-paint entry budget (Refs #883)', () => {
  const budgetPath = path.join(WEB_ROOT, 'scripts', 'bundle-size-budget.json');
  const eslintPath = path.join(WEB_ROOT, 'eslint.config.js');

  it('keeps js-entry at or under the 178000 B gzip acceptance cap with 5% headroom', () => {
    const budget = JSON.parse(readFileSync(budgetPath, 'utf8'));
    const entry = budget.rules.find((rule) => rule.id === 'js-entry');

    expect(entry).toEqual(expect.objectContaining({
      match: 'assets/index-*.js',
    }));
    expect(entry.measuredGzipBytes).toBeLessThanOrEqual(178_000);
    expect(entry.maxGzipBytes).toBeGreaterThanOrEqual(Math.ceil(entry.measuredGzipBytes * 1.05));
    expect(entry.maxGzipBytes).toBeLessThan(195_814);
  });

  it('does not add a named TimePicker budget', () => {
    const budget = JSON.parse(readFileSync(budgetPath, 'utf8'));
    expect(budget.rules.some((rule) => rule.id === 'TimePicker')).toBe(false);
  });

  it('forbids the shared control barrel from App, main, and layout', () => {
    const source = readFileSync(eslintPath, 'utf8');

    expect(source).toContain("'src/App.tsx'");
    expect(source).toContain("'src/main.tsx'");
    expect(source).toContain('src/components/layout/**/*.{ts,tsx}');
    expect(source).toContain("'no-restricted-imports'");
    expect(source).toContain("'./components/common'");
    expect(source).toContain("'../common'");
  });
});
