const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const desktopRoot = path.resolve(__dirname, '..');
const packageJson = require('../package.json');

test('desktop package pins the upgraded electron stack from issue #615', () => {
  // Runtime: Electron 43.3.0 is outside the 39.x-42.x vulnerable ranges for the
  // 2026 Electron GHSA/CVE series (e.g. GHSA-9f4c-93c8-jc8g / CVE-2026-70608).
  // Updater: 6.8.9 is above GHSA-9jxc-qjr9-vjxq / CVE-2024-39698 (<=6.3.0-alpha.5).
  // Builder: 26.15.7 replaces the audited-high 24.x packaging graph.
  assert.equal(packageJson.dependencies['electron-updater'], '6.8.9');
  assert.equal(packageJson.devDependencies.electron, '43.3.0');
  assert.equal(packageJson.devDependencies['electron-builder'], '26.15.7');
  // tar 7.5.22 is past GHSA-23hp-3jrh-7fpw / GHSA-r292-9mhp-454m and related 7.5.x pins.
  assert.equal(packageJson.overrides['app-builder-lib'].tar, '7.5.22');
  // electron-updater (production) and the builder chain both depend on js-yaml;
  // pin the 4.x graph past GHSA-5p4m-2wfm-xmqj, which has no assigned CVE ID.
  // CVE-2026-59870 belongs to the separate GHSA-724g-mxrg-4qvm record for 5.x.
  assert.equal(packageJson.overrides['js-yaml'], '4.3.1');
  assert.ok(packageJson.devDependencies.eslint, 'eslint is a desktop devDependency');
  assert.equal(packageJson.scripts.lint, 'eslint .');
  assert.equal(packageJson.scripts.typecheck, 'tsc -p jsconfig.json --noEmit');
});

test('desktop eslint flat config is present and lint is clean', () => {
  const configPath = path.join(desktopRoot, 'eslint.config.js');
  assert.ok(fs.existsSync(configPath), 'eslint.config.js must exist');

  const result = spawnSync(
    process.execPath,
    [path.join(desktopRoot, 'node_modules', 'eslint', 'bin', 'eslint.js'), '.'],
    {
      cwd: desktopRoot,
      encoding: 'utf8',
      env: process.env,
    }
  );

  assert.equal(result.status, 0, result.stdout + result.stderr);
});

test('main.js enables // @ts-check style checking', () => {
  const mainSource = fs.readFileSync(path.join(desktopRoot, 'main.js'), 'utf8');
  assert.match(mainSource, /^\/\/ @ts-check\r?\n/);
  assert.ok(fs.existsSync(path.join(desktopRoot, 'jsconfig.json')));
});
