const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const desktopRoot = path.resolve(__dirname, '..');
const packageJson = require('../package.json');

test('desktop package pins the upgraded electron stack from issue #615', () => {
  assert.equal(packageJson.dependencies['electron-updater'], '6.8.9');
  assert.equal(packageJson.devDependencies.electron, '43.3.0');
  assert.equal(packageJson.devDependencies['electron-builder'], '26.15.7');
  assert.equal(packageJson.overrides['app-builder-lib'].tar, '7.5.22');
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
