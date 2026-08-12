'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const guidance = require('../cli-operator-guidance');

test('renderer guidance never includes raw PATH or absolute executable paths', () => {
  const payload = guidance.buildCliOperatorGuidance({
    schemaVersion: 2,
    generatedAt: '2026-08-12T00:00:00.000Z',
    platform: 'darwin',
    path: {
      effectiveEntryCount: 4,
      limited: false,
      augmented: true,
      macHomebrewAugmented: true,
      policy: 'macos-gui-homebrew-extend',
      // Intentionally hostile fields that must be stripped.
      effectiveEntries: ['/opt/homebrew/bin', '/Users/operator/bin'],
      appDir: '/Users/operator/Library/Application Support/StockPulse',
    },
    cli: [
      { name: 'codex', status: 'missing', reason: null, absolutePath: '/opt/homebrew/bin/codex' },
      { name: 'claude', status: 'unknown', reason: 'probe_error' },
      { name: 'ollama', status: 'available', reason: null },
    ],
  }, { locale: 'en' });

  const serialized = JSON.stringify(payload);
  assert.equal(serialized.includes('/opt/homebrew'), false);
  assert.equal(serialized.includes('/Users/'), false);
  assert.equal(serialized.includes('Application Support'), false);
  assert.equal(serialized.includes('absolutePath'), false);
  assert.equal(serialized.includes('effectiveEntries'), false);
  assert.equal(serialized.includes('appDir'), false);
  assert.equal(payload.commands[0].status, 'missing');
  assert.equal(payload.commands[0].installGuideAvailable, true);
  assert.match(payload.commands[0].hint, /Install it on your login PATH/i);
  assert.equal(payload.copy.openTerminal.includes('/'), false);
});

test('fail-open is rejected: unknown stays unknown and available is never invented', () => {
  const payload = guidance.buildCliOperatorGuidance({
    platform: 'linux',
    path: { effectiveEntryCount: 0, limited: false, augmented: false, policy: 'inherit-process-path' },
    cli: [
      { name: 'codex', status: 'unknown', reason: 'path_unavailable' },
      { name: 'claude', status: 'unknown', reason: 'deadline_exceeded' },
    ],
  }, { locale: 'zh' });

  assert.ok(payload.needsAction);
  assert.equal(payload.commands.every((entry) => entry.status === 'unknown'), true);
  assert.ok(payload.copy.pathUnavailable);
  assert.match(payload.copy.title, /可见性/);
});

test('openOperatorTerminal launches without path arguments', () => {
  const calls = [];
  const result = guidance.openOperatorTerminal({
    platform: 'darwin',
    spawnImpl: (command, args, options) => {
      calls.push({ command, args, options });
      return { unref() {} };
    },
  });
  assert.equal(result.ok, true);
  assert.deepEqual(calls[0].command, 'open');
  assert.deepEqual(calls[0].args, ['-a', 'Terminal']);
  assert.equal(JSON.stringify(calls[0].args).includes('/Users'), false);
  assert.equal(JSON.stringify(calls[0].args).includes('StockPulse'), false);
});

test('install guide URLs stay on the HTTPS allowlist and expose host only', async () => {
  const opened = [];
  const result = await guidance.openCliInstallGuide('opencode', {
    openExternal: async (url) => {
      opened.push(url);
    },
  });
  assert.equal(result.ok, true);
  assert.equal(result.urlHost, 'opencode.ai');
  assert.equal(opened[0].startsWith('https://'), true);
  assert.equal(guidance.resolveCliInstallGuideUrl('not-a-cli'), null);
});

test('deep-link rejection copy never echoes a raw URL', () => {
  const copy = guidance.getDeepLinkRejectionCopy('en');
  assert.match(copy.title, /Unsupported/i);
  assert.equal(copy.message.includes('stockpulse://evil'), false);
  assert.equal(copy.message.includes('?secret='), false);
});
