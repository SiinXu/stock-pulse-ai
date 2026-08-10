const assert = require('node:assert/strict');
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

test('executable search entries preserve cwd and relative PATH semantics', () => {
  const posix = desktopEnv.executableSearchPathEntries(':/opt/bin:tools', {
    platform: 'linux',
    cwd: '/srv/app',
    pathImpl: path.posix,
  });
  assert.deepEqual(posix.entries, ['/srv/app', '/opt/bin', '/srv/app/tools']);

  const windows = desktopEnv.executableSearchPathEntries('"C:\\Program Files\\CLI";.\\bin;', {
    platform: 'win32',
    cwd: 'C:\\StockPulse',
    pathImpl: path.win32,
  });
  assert.deepEqual(windows.entries, [
    'C:\\Program Files\\CLI',
    'C:\\StockPulse\\bin',
    'C:\\StockPulse',
  ]);
});

test('buildDesktopEnvironmentDiagnostics reports only a path-safe summary', async () => {
  const binDir = '/private/operator/bin';
  const diagnostics = await desktopEnv.buildDesktopEnvironmentDiagnostics({
    platform: 'darwin',
    sourceEnv: { PATH: binDir },
    probeCandidate: async (candidatePath) => (
      candidatePath === `${binDir}/ollama` ? 'available' : 'missing'
    ),
    nowMs: Date.parse('2026-08-08T12:00:00.000Z'),
  });

  assert.equal(diagnostics.schemaVersion, 2);
  assert.equal(diagnostics.generatedAt, '2026-08-08T12:00:00.000Z');
  assert.equal(diagnostics.platform, 'darwin');
  assert.equal(diagnostics.path.macHomebrewAugmented, true);
  assert.equal(diagnostics.path.policy, 'macos-gui-homebrew-extend');

  const byName = Object.fromEntries(diagnostics.cli.map((entry) => [entry.name, entry]));
  assert.equal(byName.ollama.status, 'available');
  assert.equal(byName.codex.status, 'missing');
  assert.equal(byName.claude.status, 'missing');
  assert.equal(byName.opencode.status, 'missing');

  const serialized = JSON.stringify(diagnostics);
  assert.equal(serialized.includes(binDir), false);
  assert.equal(serialized.includes('/opt/homebrew/bin'), false);
  assert.equal(serialized.includes('effectiveEntries'), false);
  assert.equal(serialized.includes('appDir'), false);
  assert.equal(serialized.includes('envFile'), false);

  const summary = desktopEnv.summarizeDesktopEnvironmentDiagnostics(diagnostics);
  assert.match(summary, /platform=darwin/);
  assert.match(summary, /pathAugmented=yes/);
  assert.match(summary, /ollama=available/);
  assert.match(summary, /codex=missing/);
  assert.equal(summary.includes(binDir), false);
});

test('diagnostics use path.win32 PATHEXT rules independent of the host', async () => {
  const seen = [];
  const diagnostics = await desktopEnv.buildDesktopEnvironmentDiagnostics({
    platform: 'win32',
    cwd: 'C:\\StockPulse',
    sourceEnv: {
      PATH: '"C:\\Program Files\\CLI";.\\bin',
      PATHEXT: '.EXE;.CMD',
    },
    commands: ['codex'],
    pathImpl: path.win32,
    probeCandidate: async (candidatePath) => {
      seen.push(candidatePath);
      return candidatePath === 'C:\\Program Files\\CLI\\codex.CMD'
        ? 'available'
        : 'missing';
    },
  });
  assert.equal(diagnostics.cli[0].status, 'available');
  assert.ok(seen.includes('C:\\Program Files\\CLI\\codex.EXE'));
  assert.ok(seen.includes('C:\\Program Files\\CLI\\codex.CMD'));
  assert.ok(seen.includes('C:\\StockPulse\\bin\\codex.EXE'));
});

test('slow and errored probes remain unknown instead of false missing', async () => {
  const timedOut = await desktopEnv.buildDesktopEnvironmentDiagnostics({
    platform: 'linux',
    sourceEnv: { PATH: '/slow/mount' },
    commands: ['codex'],
    deadlineMs: 5,
    probeCandidate: () => new Promise(() => undefined),
  });
  assert.deepEqual(timedOut.cli[0], {
    name: 'codex',
    status: 'unknown',
    reason: 'deadline_exceeded',
  });

  const errored = await desktopEnv.buildDesktopEnvironmentDiagnostics({
    platform: 'linux',
    sourceEnv: { PATH: '/broken/mount' },
    commands: ['codex'],
    probeCandidate: async () => 'unknown',
  });
  assert.equal(errored.cli[0].status, 'unknown');
  assert.equal(errored.cli[0].reason, 'probe_error');
});

test('permission failures remain unknown instead of false missing', async () => {
  const diagnostics = await desktopEnv.buildDesktopEnvironmentDiagnostics({
    platform: 'linux',
    sourceEnv: { PATH: '/restricted/mount' },
    commands: ['codex'],
    probeCandidate: async (candidatePath, options) => desktopEnv.probeExecutableCandidate(
      candidatePath,
      {
        ...options,
        fsPromises: {
          access: async () => {
            const error = new Error('permission denied');
            error.code = 'EACCES';
            throw error;
          },
          stat: async () => ({ isFile: () => true }),
        },
      }
    ),
  });
  assert.deepEqual(diagnostics.cli[0], {
    name: 'codex',
    status: 'unknown',
    reason: 'probe_error',
  });
});

test('missing PATH is unknown and non-macOS policy stays inherit-only', async () => {
  const diagnostics = await desktopEnv.buildDesktopEnvironmentDiagnostics({
    platform: 'linux',
    sourceEnv: {},
    commands: ['codex'],
  });
  assert.equal(diagnostics.path.policy, 'inherit-process-path');
  assert.equal(diagnostics.path.augmented, false);
  assert.deepEqual(diagnostics.cli[0], {
    name: 'codex',
    status: 'unknown',
    reason: 'path_unavailable',
  });
});

test('diagnostic probe is single-flight and caches completed results', async () => {
  let buildCalls = 0;
  let now = 100;
  let releaseBuild;
  const buildResult = { schemaVersion: 2, cli: [] };
  const probe = desktopEnv.createDesktopEnvironmentDiagnosticsProbe({
    cacheTtlMs: 50,
    clock: () => now,
    build: () => {
      buildCalls += 1;
      return new Promise((resolve) => {
        releaseBuild = () => resolve(buildResult);
      });
    },
  });

  const first = probe();
  const second = probe();
  assert.strictEqual(first, second);
  await Promise.resolve();
  releaseBuild();
  assert.strictEqual(await first, buildResult);
  assert.strictEqual(await probe(), buildResult);
  assert.equal(buildCalls, 1);

  now += 51;
  const refreshed = probe();
  await Promise.resolve();
  releaseBuild();
  await refreshed;
  assert.equal(buildCalls, 2);
});
