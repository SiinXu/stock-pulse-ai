const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const desktopEnv = require('../desktop-env');

test('extendMacDesktopBackendPath appends Homebrew and system entries without duplicates', () => {
  const extended = desktopEnv.extendMacDesktopBackendPath(
    '/usr/bin:/bin:/opt/homebrew/bin',
    'darwin'
  );
  const entries = extended.split(':');
  assert.deepEqual(entries.slice(0, 3), ['/usr/bin', '/bin', '/opt/homebrew/bin']);
  assert.ok(entries.includes('/usr/local/bin'));
  assert.ok(entries.includes('/usr/sbin'));
  assert.equal(entries.filter((entry) => entry === '/opt/homebrew/bin').length, 1);
});

test('extendMacDesktopBackendPath is a no-op outside macOS', () => {
  assert.equal(
    desktopEnv.extendMacDesktopBackendPath('/custom/bin:/usr/bin', 'linux'),
    '/custom/bin:/usr/bin'
  );
  assert.equal(
    desktopEnv.extendMacDesktopBackendPath('C:\\Windows\\System32', 'win32'),
    'C:\\Windows\\System32'
  );
});

test('resolveCommandOnPath finds executable basenames on effective PATH', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-env-cli-'));
  t.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }));

  const binDir = path.join(tempRoot, 'bin');
  fs.mkdirSync(binDir, { recursive: true });
  const codexPath = path.join(binDir, 'codex');
  fs.writeFileSync(codexPath, '#!/bin/sh\necho ok\n', { mode: 0o755 });
  fs.chmodSync(codexPath, 0o755);

  assert.equal(
    desktopEnv.resolveCommandOnPath('codex', `${binDir}:/usr/bin`, { platform: 'darwin' }),
    codexPath
  );
  assert.equal(
    desktopEnv.resolveCommandOnPath('missing-cli', `${binDir}:/usr/bin`, { platform: 'darwin' }),
    null
  );
  assert.equal(
    desktopEnv.resolveCommandOnPath('../escape', binDir, { platform: 'darwin' }),
    null
  );
  assert.equal(
    desktopEnv.resolveCommandOnPath('codex;rm', binDir, { platform: 'darwin' }),
    null
  );
});

test('resolveCommandOnPath accepts Windows .exe candidates', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-env-win-'));
  t.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }));

  const binDir = path.join(tempRoot, 'bin');
  fs.mkdirSync(binDir, { recursive: true });
  const ollamaPath = path.join(binDir, 'ollama.exe');
  fs.writeFileSync(ollamaPath, 'MZ');

  assert.equal(
    desktopEnv.resolveCommandOnPath('ollama', binDir, { platform: 'win32' }),
    ollamaPath
  );
});

test('buildDesktopEnvironmentDiagnostics reports PATH augmentation and CLI visibility', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-env-diag-'));
  t.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }));

  const binDir = path.join(tempRoot, 'bin');
  fs.mkdirSync(binDir, { recursive: true });
  const ollamaPath = path.join(binDir, 'ollama');
  fs.writeFileSync(ollamaPath, '#!/bin/sh\n', { mode: 0o755 });
  fs.chmodSync(ollamaPath, 0o755);
  const envFile = path.join(tempRoot, '.env');
  fs.writeFileSync(envFile, 'GENERATION_BACKEND=litellm\n', 'utf-8');

  const diagnostics = desktopEnv.buildDesktopEnvironmentDiagnostics({
    platform: 'darwin',
    sourceEnv: { PATH: binDir },
    appDir: tempRoot,
    envFile,
    nowMs: Date.parse('2026-08-08T12:00:00.000Z'),
  });

  assert.equal(diagnostics.schemaVersion, 1);
  assert.equal(diagnostics.generatedAt, '2026-08-08T12:00:00.000Z');
  assert.equal(diagnostics.platform, 'darwin');
  assert.equal(diagnostics.path.macHomebrewAugmented, true);
  assert.equal(diagnostics.path.policy, 'macos-gui-homebrew-extend');
  assert.ok(diagnostics.path.effectiveEntries.includes('/opt/homebrew/bin'));
  assert.ok(diagnostics.path.effectiveEntries.includes(binDir));
  assert.equal(diagnostics.runtime.envFileExists, true);
  assert.equal(diagnostics.runtime.appDir, tempRoot);

  const byName = Object.fromEntries(diagnostics.cli.map((entry) => [entry.name, entry]));
  assert.equal(byName.ollama.found, true);
  assert.equal(byName.ollama.path, ollamaPath);
  assert.equal(byName.codex.found, false);
  assert.equal(byName.codex.path, null);
  assert.equal(byName.claude.found, false);
  assert.equal(byName.opencode.found, false);

  // Diagnostics must not echo .env values.
  const serialized = JSON.stringify(diagnostics);
  assert.equal(serialized.includes('GENERATION_BACKEND'), false);
  assert.equal(serialized.includes('litellm'), false);

  const summary = desktopEnv.summarizeDesktopEnvironmentDiagnostics(diagnostics);
  assert.match(summary, /platform=darwin/);
  assert.match(summary, /pathAugmented=yes/);
  assert.match(summary, /ollama=found/);
  assert.match(summary, /codex=missing/);
  assert.equal(summary.includes(ollamaPath), false);
});

test('buildDesktopEnvironmentDiagnostics keeps non-macOS PATH policy inherit-only', () => {
  const diagnostics = desktopEnv.buildDesktopEnvironmentDiagnostics({
    platform: 'linux',
    sourceEnv: { PATH: '/custom/bin:/usr/bin' },
    nowMs: 0,
  });
  assert.equal(diagnostics.path.policy, 'inherit-process-path');
  assert.equal(diagnostics.path.augmented, false);
  assert.equal(diagnostics.path.effective, '/custom/bin:/usr/bin');
  assert.equal(diagnostics.path.macHomebrewAugmented, false);
});
