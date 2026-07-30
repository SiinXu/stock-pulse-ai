const assert = require('node:assert/strict');
const test = require('node:test');
const { EventEmitter } = require('node:events');
const { TextDecoder } = require('node:util');

const {
  createBackendRuntime,
} = require('../backend-runtime');

const MODEL_PACK_ATTESTATION_ENV = 'STOCKPULSE_DESKTOP_MODEL_PACK_ATTESTATION_KEY';
const MODEL_PACK_ATTESTATION_KEY = 'a'.repeat(64);

function makeChild(pid) {
  const child = new EventEmitter();
  child.pid = pid;
  child.exitCode = null;
  child.signalCode = null;
  child.killed = false;
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = () => true;
  return child;
}

function makeRuntime(options = {}) {
  const unavailableSnapshots = [];
  const logs = [];
  const runtime = createBackendRuntime({
    appRootDev: '/tmp/stockpulse',
    isWindows: false,
    isMac: false,
    spawnImpl: () => makeChild(1),
    netImpl: {
      createServer: () => {
        throw new Error('Unexpected port allocation');
      },
    },
    httpImpl: {
      get: () => {
        throw new Error('Unexpected health request');
      },
    },
    TextDecoderImpl: TextDecoder,
    modelPackAttestationEnv: MODEL_PACK_ATTESTATION_ENV,
    modelPackAttestationKey: MODEL_PACK_ATTESTATION_KEY,
    getIsPackaged: () => false,
    getResourcesPath: () => '/tmp/resources',
    getSourceEnv: () => ({}),
    resolveEnvExamplePath: () => '/tmp/.env.example',
    logLine: (line) => logs.push(line),
    onUnavailable: (snapshot) => unavailableSnapshots.push(snapshot),
    ...options,
  });
  return { runtime, unavailableSnapshots, logs };
}

test('waitUntilHealthy resolves one successful probe and preserves the current generation', async () => {
  const child = makeChild(1001);
  const progress = [];
  const httpImpl = {
    get: (_url, onResponse) => {
      const request = new EventEmitter();
      request.destroyed = false;
      request.setTimeout = () => undefined;
      request.destroy = () => {
        request.destroyed = true;
      };
      process.nextTick(() => {
        onResponse({
          statusCode: 200,
          resume: () => undefined,
        });
      });
      return request;
    },
  };
  const { runtime } = makeRuntime({ httpImpl });
  runtime.setProcessForTest(child);

  const result = await runtime.waitUntilHealthy({
    url: 'http://127.0.0.1:8123/api/health',
    timeoutMs: 50,
    intervalMs: 1,
    requestTimeoutMs: 10,
    onProgress: (event) => progress.push(event.type),
  });

  assert.equal(result.attempts, 1);
  assert.deepEqual(progress, ['probe_start', 'ready']);
  assert.equal(runtime.getSnapshot().process, child);
  assert.equal(runtime.getSnapshot().startError, null);
});

test('waitUntilHealthy records probe and total timeout diagnostics', async () => {
  const child = makeChild(1002);
  const progress = [];
  const httpImpl = {
    get: () => {
      const request = new EventEmitter();
      request.destroyed = false;
      request.setTimeout = (_timeoutMs, handler) => {
        setImmediate(handler);
      };
      request.destroy = (error) => {
        request.destroyed = true;
        if (error) {
          process.nextTick(() => request.emit('error', error));
        }
      };
      return request;
    },
  };
  const { runtime, unavailableSnapshots } = makeRuntime({ httpImpl });
  runtime.setProcessForTest(child);

  await assert.rejects(
    runtime.waitUntilHealthy({
      url: 'http://127.0.0.1:8123/api/health',
      timeoutMs: 5,
      intervalMs: 1,
      requestTimeoutMs: 1,
      onProgress: (event) => progress.push(event.type),
    }),
    /Health check timeout/
  );

  assert.ok(progress.includes('probe_timeout'));
  assert.ok(progress.includes('total_timeout'));
  assert.equal(progress.at(-1), 'final_error');
  assert.match(runtime.getSnapshot().startError.message, /Health check timeout/);
  assert.equal(unavailableSnapshots.length, 1);
});

test('startBackend owns synchronous spawn failures and publishes an unavailable snapshot', () => {
  const spawnError = new Error('synchronous spawn failure');
  const { runtime, unavailableSnapshots } = makeRuntime({
    spawnImpl: () => {
      throw spawnError;
    },
  });

  assert.throws(
    () => runtime.startBackend({
      port: 8123,
      envFile: '/tmp/.env',
      dbPath: '/tmp/stock_analysis.db',
      logDir: '/tmp/logs',
    }),
    /synchronous spawn failure/
  );

  assert.equal(runtime.getSnapshot().process, null);
  assert.equal(runtime.getSnapshot().startError, spawnError);
  assert.equal(unavailableSnapshots.length, 1);
  assert.equal(unavailableSnapshots[0].startError, spawnError);
});

test('replaced backend generations cannot mutate runtime state or logs', () => {
  const children = [makeChild(2001), makeChild(2002)];
  let spawnIndex = 0;
  const { runtime, unavailableSnapshots, logs } = makeRuntime({
    spawnImpl: () => children[spawnIndex++],
  });
  const launchOptions = {
    port: 8123,
    envFile: '/tmp/.env',
    dbPath: '/tmp/stock_analysis.db',
    logDir: '/tmp/logs',
  };

  runtime.startBackend(launchOptions);
  runtime.startBackend({ ...launchOptions, port: 8124 });
  children[0].stdout.emit('data', 'stale output');
  children[0].emit('error', new Error('stale error'));
  children[0].emit('exit', 1, null);

  assert.equal(runtime.getSnapshot().process, children[1]);
  assert.equal(runtime.getSnapshot().startError, null);
  assert.equal(unavailableSnapshots.length, 0);
  assert.ok(logs.every((line) => !line.includes('stale')));

  children[1].emit('error', new Error('current error'));
  assert.match(runtime.getSnapshot().startError.message, /current error/);
  assert.equal(unavailableSnapshots.length, 1);
});

test('stopBackend waits for POSIX child exit before clearing the owned process', async () => {
  const child = makeChild(3001);
  const signals = [];
  child.kill = (signal) => {
    signals.push(signal);
    process.nextTick(() => {
      child.exitCode = 0;
      child.emit('exit', 0, null);
    });
    return true;
  };
  const { runtime } = makeRuntime();
  runtime.setProcessForTest(child);

  await runtime.stopBackend();

  assert.deepEqual(signals, ['SIGTERM']);
  assert.equal(runtime.getSnapshot().process, null);
});
