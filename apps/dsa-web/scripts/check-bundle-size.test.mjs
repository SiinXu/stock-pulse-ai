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

function writeBudget(root, rules, aggregateRules) {
  const budgetPath = path.join(root, 'budget.json');
  const budget = {
    version: 1,
    outDir: root,
    gzipLevel: 9,
    defaults: {
      jsMaxGzipBytes: 1_000_000,
      cssMaxGzipBytes: 1_000_000,
    },
    rules,
  };
  if (aggregateRules !== undefined) {
    budget.aggregateRules = aggregateRules;
  }
  writeFileSync(budgetPath, JSON.stringify(budget));
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

describe('bundle size aggregate families (Refs #883)', () => {
  const familyContents = Buffer.from("export const family = 'aggregate-guard';\n".repeat(48));

  function writeHashedAsset(root, name, contents = familyContents) {
    writeFileSync(path.join(root, 'assets', name), contents);
    return gzipSync(contents, { level: 9 }).length;
  }

  it('accepts a family whose unique matched gzip total is exactly at the aggregate cap', () => {
    const root = createOutput();
    const leftGzip = writeHashedAsset(root, 'ContractChunk-aaa.js');
    const rightGzip = writeHashedAsset(root, 'ContractChunk-bbb.js', Buffer.from("export const extra = 'split';\n".repeat(32)));
    const unrelatedGzip = writeHashedAsset(
      root,
      'vendor-charts-ccc.js',
      Buffer.from("export const charts = 'unrelated';\n".repeat(40)),
    );
    const budgetPath = writeBudget(
      root,
      [],
      [{
        id: 'contract-family',
        match: ['assets/ContractChunk-*.js', 'assets/ContractChunk*.js'],
        maxGzipBytes: leftGzip + rightGzip,
      }],
    );

    const result = runChecker(budgetPath);
    const familyBlock = result.stdout.slice(result.stdout.indexOf('bundle-size: aggregate families:'));

    expect(result.status).toBe(0);
    expect(familyBlock).toContain('[OK] contract-family');
    expect(familyBlock).toContain(`gzip=${leftGzip + rightGzip} B`);
    expect(familyBlock).toContain('assets/ContractChunk-aaa.js');
    expect(familyBlock).toContain('assets/ContractChunk-bbb.js');
    expect(familyBlock).not.toContain('vendor-charts-ccc.js');
    expect(unrelatedGzip).toBeGreaterThan(0);
    expect(result.stdout).toContain('1 aggregate family within budget');
  });

  it('fails a split-bypass where each sibling is under the per-asset cap but the family total is not', () => {
    const root = createOutput();
    const leftGzip = writeHashedAsset(root, 'ContractChunk-aaa.js');
    const rightGzip = writeHashedAsset(root, 'ContractChunk-bbb.js', Buffer.from("export const extra = 'split';\n".repeat(32)));
    const perAssetCap = Math.max(leftGzip, rightGzip);
    const budgetPath = writeBudget(
      root,
      [{
        id: 'contract',
        match: 'assets/ContractChunk-*.js',
        maxGzipBytes: perAssetCap,
      }],
      [{
        id: 'contract-family',
        match: 'assets/ContractChunk-*.js',
        maxGzipBytes: perAssetCap,
      }],
    );

    const result = runChecker(budgetPath);

    expect(leftGzip).toBeLessThanOrEqual(perAssetCap);
    expect(rightGzip).toBeLessThanOrEqual(perAssetCap);
    expect(leftGzip + rightGzip).toBeGreaterThan(perAssetCap);
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('FAIL contract-family');
    expect(result.stderr).toContain(`gzip=${leftGzip + rightGzip} B`);
    expect(result.stderr).toContain(`budget=${perAssetCap} B`);
    expect(result.stderr).toContain('assets/ContractChunk-aaa.js, assets/ContractChunk-bbb.js');
    expect(result.stderr).toContain('aggregate family exceeded budget');
    expect(result.stdout).toContain('assets=2');
  });

  it('counts overlapping family globs once so a renamed hash cannot be double-billed', () => {
    const root = createOutput();
    const gzipBytes = writeHashedAsset(root, 'ContractChunk-renamedHash.js');
    const budgetPath = writeBudget(
      root,
      [],
      [{
        id: 'contract-family',
        match: ['assets/ContractChunk-*.js', 'assets/ContractChunk-renamedHash.js'],
        maxGzipBytes: gzipBytes,
      }],
    );

    const result = runChecker(budgetPath);
    const familyBlock = result.stdout.slice(result.stdout.indexOf('bundle-size: aggregate families:'));

    expect(result.status).toBe(0);
    expect(familyBlock).toContain(`gzip=${gzipBytes} B`);
    expect(familyBlock).toContain('assets=1');
    expect(familyBlock.match(/assets\/ContractChunk-renamedHash\.js/g)).toHaveLength(1);
  });

  it('fails when an aggregate rule matches no artifact', () => {
    const root = createOutput();
    writeHashedAsset(root, 'OtherChunk-hash.js');
    const budgetPath = writeBudget(
      root,
      [],
      [{
        id: 'contract-family',
        match: 'assets/ContractChunk-*.js',
        maxGzipBytes: 1_000_000,
      }],
    );

    const result = runChecker(budgetPath);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain(
      'Aggregate rule matched no build artifact: contract-family.',
    );
  });

  it('keeps budgets without aggregateRules backward compatible', () => {
    const root = createOutput();
    const gzipBytes = writeHashedAsset(root, 'ContractChunk-hash.js');
    const budgetPath = writeBudget(root, [{
      id: 'contract',
      match: 'assets/ContractChunk-*.js',
      maxGzipBytes: gzipBytes,
    }]);

    const result = runChecker(budgetPath);

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('bundle-size: OK — 1 assets within budget');
    expect(result.stdout).not.toContain('aggregate family');
  });
});

describe('criticalPath aggregate family (Refs #883)', () => {
  const entryContents = Buffer.from("export const entry = 'critical-path-entry';\n".repeat(48));
  const splitContents = Buffer.from("export const split = 'critical-path-sibling';\n".repeat(40));

  function writeHashedAsset(root, name, contents) {
    writeFileSync(path.join(root, 'assets', name), contents);
    return gzipSync(contents, { level: 9 }).length;
  }

  function writeIndexHtml(root, { entry, modulepreloads = [] }) {
    const preloadTags = modulepreloads
      .map((href) => `<link rel="modulepreload" crossorigin href="/${href}">`)
      .join('\n');
    writeFileSync(
      path.join(root, 'index.html'),
      `<!doctype html><html><head>
<script>window.__theme = 'dark';</script>
<script type="module" crossorigin src="/${entry}"></script>
${preloadTags}
<link rel="stylesheet" href="/assets/index-not-critical.css">
</head><body></body></html>`,
    );
  }

  function criticalPathRule(maxGzipBytes, extra = {}) {
    return {
      id: 'criticalPath',
      source: 'indexHtmlModulepreload',
      match: ['assets/index-*.js'],
      maxGzipBytes,
      ...extra,
    };
  }

  it('sums the entry script and modulepreload hrefs at the exact family cap', () => {
    const root = createOutput();
    const entryGzip = writeHashedAsset(root, 'index-aaa.js', entryContents);
    const vendorGzip = writeHashedAsset(root, 'vendor-react-bbb.js', splitContents);
    writeHashedAsset(
      root,
      'HomePage-ccc.js',
      Buffer.from("export const lazy = 'not-on-critical-path';\n".repeat(32)),
    );
    writeIndexHtml(root, {
      entry: 'assets/index-aaa.js',
      modulepreloads: ['assets/vendor-react-bbb.js'],
    });
    const budgetPath = writeBudget(
      root,
      [],
      [criticalPathRule(entryGzip + vendorGzip)],
    );

    const result = runChecker(budgetPath);
    const familyBlock = result.stdout.slice(result.stdout.indexOf('bundle-size: aggregate families:'));

    expect(result.status).toBe(0);
    expect(familyBlock).toContain('[OK] criticalPath');
    expect(familyBlock).toContain(`gzip=${entryGzip + vendorGzip} B`);
    expect(familyBlock).toContain('assets/index-aaa.js');
    expect(familyBlock).toContain('assets/vendor-react-bbb.js');
    expect(familyBlock).not.toContain('HomePage-ccc.js');
    expect(result.stdout).toContain('1 aggregate family within budget');
  });

  it('fails a renamed split that evades the match glob but stays on the modulepreload graph', () => {
    const root = createOutput();
    const entryGzip = writeHashedAsset(root, 'index-aaa.js', entryContents);
    const siblingGzip = writeHashedAsset(root, 'vendor-split-bbb.js', splitContents);
    const perAssetCap = Math.max(entryGzip, siblingGzip);
    writeIndexHtml(root, {
      entry: 'assets/index-aaa.js',
      modulepreloads: ['assets/vendor-split-bbb.js'],
    });
    const budgetPath = writeBudget(
      root,
      [
        {
          id: 'js-entry',
          match: 'assets/index-*.js',
          maxGzipBytes: perAssetCap,
        },
      ],
      [criticalPathRule(perAssetCap)],
    );

    const result = runChecker(budgetPath);

    expect(entryGzip).toBeLessThanOrEqual(perAssetCap);
    expect(siblingGzip).toBeLessThanOrEqual(perAssetCap);
    expect(entryGzip + siblingGzip).toBeGreaterThan(perAssetCap);
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('FAIL criticalPath');
    expect(result.stderr).toContain(`gzip=${entryGzip + siblingGzip} B`);
    expect(result.stderr).toContain(`budget=${perAssetCap} B`);
    expect(result.stderr).toContain('assets/index-aaa.js, assets/vendor-split-bbb.js');
    expect(result.stderr).toContain('aggregate family exceeded budget');
    expect(result.stdout).toContain('assets=2');
  });

  it('does not bill a glob-matching sibling that is absent from index.html', () => {
    const root = createOutput();
    const entryGzip = writeHashedAsset(root, 'index-aaa.js', entryContents);
    writeHashedAsset(root, 'index-extra.js', splitContents);
    writeIndexHtml(root, { entry: 'assets/index-aaa.js' });
    const budgetPath = writeBudget(
      root,
      [],
      [criticalPathRule(entryGzip)],
    );

    const result = runChecker(budgetPath);
    const familyBlock = result.stdout.slice(result.stdout.indexOf('bundle-size: aggregate families:'));

    expect(result.status).toBe(0);
    expect(familyBlock).toContain(`gzip=${entryGzip} B`);
    expect(familyBlock).toContain('assets=1');
    expect(familyBlock).toContain('assets/index-aaa.js');
    expect(familyBlock).not.toContain('index-extra.js');
  });

  it('counts an entry that is also modulepreloaded once', () => {
    const root = createOutput();
    const entryGzip = writeHashedAsset(root, 'index-aaa.js', entryContents);
    writeIndexHtml(root, {
      entry: 'assets/index-aaa.js',
      modulepreloads: ['assets/index-aaa.js'],
    });
    const budgetPath = writeBudget(
      root,
      [],
      [criticalPathRule(entryGzip)],
    );

    const result = runChecker(budgetPath);
    const familyBlock = result.stdout.slice(result.stdout.indexOf('bundle-size: aggregate families:'));

    expect(result.status).toBe(0);
    expect(familyBlock).toContain(`gzip=${entryGzip} B`);
    expect(familyBlock).toContain('assets=1');
    expect(familyBlock.match(/assets\/index-aaa\.js/g)).toHaveLength(1);
  });

  it('fails when index.html is missing', () => {
    const root = createOutput();
    writeHashedAsset(root, 'index-aaa.js', entryContents);
    const budgetPath = writeBudget(
      root,
      [],
      [criticalPathRule(1_000_000)],
    );

    const result = runChecker(budgetPath);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('index.html not found');
  });

  it('fails when a modulepreload href is missing from the build assets', () => {
    const root = createOutput();
    writeHashedAsset(root, 'index-aaa.js', entryContents);
    writeIndexHtml(root, {
      entry: 'assets/index-aaa.js',
      modulepreloads: ['assets/vendor-missing-bbb.js'],
    });
    const budgetPath = writeBudget(
      root,
      [],
      [criticalPathRule(1_000_000)],
    );

    const result = runChecker(budgetPath);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain(
      'Aggregate rule criticalPath references missing build artifacts: assets/vendor-missing-bbb.js.',
    );
  });

  it('fails closed when criticalPath is missing the indexHtmlModulepreload source', () => {
    const root = createOutput();
    writeHashedAsset(root, 'index-aaa.js', entryContents);
    writeIndexHtml(root, { entry: 'assets/index-aaa.js' });
    const budgetPath = writeBudget(
      root,
      [],
      [{
        id: 'criticalPath',
        match: 'assets/index-*.js',
        maxGzipBytes: 1_000_000,
      }],
    );

    const result = runChecker(budgetPath);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain(
      'Aggregate rule criticalPath requires source "indexHtmlModulepreload"',
    );
  });

  it('fails closed on an unknown aggregate source', () => {
    const root = createOutput();
    writeHashedAsset(root, 'index-aaa.js', entryContents);
    const budgetPath = writeBudget(
      root,
      [],
      [{
        id: 'contract-family',
        match: 'assets/index-*.js',
        source: 'invented',
        maxGzipBytes: 1_000_000,
      }],
    );

    const result = runChecker(budgetPath);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('Aggregate rule contract-family has unknown source: invented');
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

  it('adds same-pattern aggregate families without raising per-asset caps or residual vendor-misc', () => {
    const budget = JSON.parse(readFileSync(budgetPath, 'utf8'));
    const residualIds = new Set(['vendor-misc']);
    const aggregateIds = budget.aggregateRules.map((rule) => rule.id);

    expect(new Set(aggregateIds).size).toBe(aggregateIds.length);
    expect(aggregateIds).not.toContain('vendor-misc-family');

    for (const rule of budget.rules) {
      if (residualIds.has(rule.id)) {
        continue;
      }
      const family = budget.aggregateRules.find((entry) => entry.id === `${rule.id}-family`);
      expect(family, `missing family for ${rule.id}`).toEqual(expect.objectContaining({
        match: [rule.match],
      }));
      expect(family.measuredGzipBytes).toBeGreaterThan(0);
      expect(family.maxGzipBytes).toBeGreaterThanOrEqual(family.measuredGzipBytes);
      if (!rule.id.startsWith('locale-')) {
        expect(family.maxGzipBytes).toBe(rule.maxGzipBytes);
      } else {
        expect(family.maxGzipBytes).toBe(family.measuredGzipBytes + 400);
        expect(family.maxGzipBytes).toBeGreaterThan(rule.maxGzipBytes);
      }
    }

    const entryFamily = budget.aggregateRules.find((rule) => rule.id === 'js-entry-family');
    const entry = budget.rules.find((rule) => rule.id === 'js-entry');
    expect(entryFamily.maxGzipBytes).toBe(entry.maxGzipBytes);
    expect(entryFamily.maxGzipBytes).toBeLessThan(195_814);

    for (const routeId of ['settings-route', 'portfolio-route', 'screening-route', 'home-watchlist-route', 'backtest-route']) {
      const route = budget.aggregateRules.find((rule) => rule.id === routeId);
      expect(route, routeId).toBeTruthy();
      expect(Array.isArray(route.match)).toBe(true);
      expect(route.match.length).toBeGreaterThan(1);
      expect(route.maxGzipBytes).toBe(route.measuredGzipBytes + 400);
    }

    const backtestRoute = budget.aggregateRules.find((rule) => rule.id === 'backtest-route');
    expect(backtestRoute.match).toEqual([
      'assets/BacktestPage-*.js',
      'assets/Backtest*-*.js',
      'assets/backtest*-*.js',
    ]);
    const backtestPage = budget.rules.find((rule) => rule.id === 'BacktestPage');
    const backtestPageFamily = budget.aggregateRules.find((rule) => rule.id === 'BacktestPage-family');
    expect(backtestPageFamily.match).toEqual([backtestPage.match]);
    expect(backtestPageFamily.maxGzipBytes).toBe(backtestPage.maxGzipBytes);
  });

  it('does not bill extra-locale catalog chunks to core locale-ja family', () => {
    const budget = JSON.parse(readFileSync(budgetPath, 'utf8'));
    const jaFamily = budget.aggregateRules.find((rule) => rule.id === 'locale-ja-family');
    const extra = budget.rules.find((rule) => rule.id === 'locale-extra');
    const extraFamily = budget.aggregateRules.find((rule) => rule.id === 'locale-extra-family');
    expect(jaFamily.match).toEqual(['assets/ja-*.js']);
    expect(extra.match).toBe('assets/extra-locale-*.js');
    expect(extraFamily.match).toEqual(['assets/extra-locale-*.js']);

    const toRegExp = (globPattern) => {
      const escaped = globPattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '[^/]*');
      return new RegExp(`^${escaped}$`);
    };
    const jaGlob = toRegExp(jaFamily.match[0]);
    const extraGlob = toRegExp(extra.match);
    expect(jaGlob.test('assets/ja-DXUJa6-A.js')).toBe(true);
    expect(jaGlob.test('assets/extra-locale-ja-CjJs-L44.js')).toBe(false);
    expect(jaGlob.test('assets/optional-sections-ja-hash.js')).toBe(false);
    expect(extraGlob.test('assets/extra-locale-ja-CjJs-L44.js')).toBe(true);
    expect(extraGlob.test('assets/ja-DXUJa6-A.js')).toBe(false);
    expect(extraGlob.test('assets/optional-sections-ja-hash.js')).toBe(false);
    expect(extraFamily.maxGzipBytes).toBe(extraFamily.measuredGzipBytes + 400);
    expect(extraFamily.maxGzipBytes).toBeGreaterThan(extra.maxGzipBytes);
  });

  it('seeds criticalPath from index.html modulepreload at the measured total', () => {
    const budget = JSON.parse(readFileSync(budgetPath, 'utf8'));
    const criticalPath = budget.aggregateRules.find((rule) => rule.id === 'criticalPath');

    expect(criticalPath).toEqual(expect.objectContaining({
      id: 'criticalPath',
      source: 'indexHtmlModulepreload',
      match: ['assets/index-*.js'],
    }));
    expect(criticalPath.measuredGzipBytes).toBe(373653);
    expect(criticalPath.maxGzipBytes).toBe(criticalPath.measuredGzipBytes);
    expect(budget.aggregateRules[budget.aggregateRules.length - 1].id).toBe('criticalPath');
    expect(budget.rules.some((rule) => rule.id === 'criticalPath')).toBe(false);
  });
});
