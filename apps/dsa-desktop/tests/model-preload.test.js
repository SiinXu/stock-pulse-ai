const assert = require('node:assert/strict');
const test = require('node:test');
const Module = require('node:module');

function loadModelPreload(t, ipcRenderer, presets = [{
  id: 'qwen3:8b',
  label: 'Qwen3 8B',
  approxSizeGb: 5.2,
  minRamGb: 16,
  guidance: 'Balanced local model.',
}]) {
  const originalLoad = Module._load;
  const originalArgv = [...process.argv];
  const exposed = [];
  const preloadPath = require.resolve('../model-preload.js');
  process.argv.push(`--stockpulse-local-model-presets=${encodeURIComponent(JSON.stringify(presets))}`);

  Module._load = function patchedLoad(request, parent, isMain) {
    if (request === 'electron') {
      return {
        contextBridge: {
          exposeInMainWorld: (...args) => exposed.push(args),
        },
        ipcRenderer,
      };
    }
    return originalLoad.call(this, request, parent, isMain);
  };
  delete require.cache[preloadPath];

  t.after(() => {
    Module._load = originalLoad;
    process.argv = originalArgv;
    delete require.cache[preloadPath];
  });

  return {
    exposed,
    preloadModule: require('../model-preload.js'),
  };
}

test('model preload exposes only the minimal local model bridge', (t) => {
  const ipcRenderer = {
    invoke: async () => undefined,
    on: () => undefined,
    removeListener: () => undefined,
  };
  const { exposed } = loadModelPreload(t, ipcRenderer);

  assert.equal(exposed.length, 1);
  assert.equal(exposed[0][0], 'stockPulseLocalModels');
  assert.deepEqual(Object.keys(exposed[0][1]).sort(), [
    'detect',
    'getState',
    'onStateChange',
    'openInstallGuide',
    'presets',
    'pull',
    'register',
    'start',
    'stop',
  ]);
});

test('model bridge delegates lifecycle actions and removes state listeners', async (t) => {
  const listeners = new Map();
  const calls = [];
  const ipcRenderer = {
    invoke: async (channel, payload) => {
      calls.push({ channel, payload });
      return { channel, payload };
    },
    on: (channel, listener) => listeners.set(channel, listener),
    removeListener: (channel, listener) => {
      if (listeners.get(channel) === listener) {
        listeners.delete(channel);
      }
    },
  };
  const { preloadModule } = loadModelPreload(t, ipcRenderer);
  const bridge = preloadModule.createLocalModelBridge({ renderer: ipcRenderer });

  assert.deepEqual(await bridge.detect(), {
    channel: preloadModule.DESKTOP_LOCAL_MODEL_DETECT_CHANNEL,
    payload: undefined,
  });
  assert.deepEqual(await bridge.pull('qwen3:8b'), {
    channel: preloadModule.DESKTOP_LOCAL_MODEL_PULL_CHANNEL,
    payload: { modelId: 'qwen3:8b' },
  });
  assert.deepEqual(await bridge.register('qwen3:8b'), {
    channel: preloadModule.DESKTOP_LOCAL_MODEL_REGISTER_CHANNEL,
    payload: { modelId: 'qwen3:8b' },
  });

  const states = [];
  const unsubscribe = bridge.onStateChange((state) => states.push(state));
  listeners.get(preloadModule.DESKTOP_LOCAL_MODEL_STATE_EVENT)(null, { status: 'running' });
  unsubscribe();

  assert.deepEqual(states, [{ status: 'running' }]);
  assert.equal(listeners.has(preloadModule.DESKTOP_LOCAL_MODEL_STATE_EVENT), false);
  assert.equal(calls.length, 3);
});

test('model bridge presets are inert display metadata only', (t) => {
  const ipcRenderer = {
    invoke: async () => undefined,
    on: () => undefined,
    removeListener: () => undefined,
  };
  const { preloadModule } = loadModelPreload(t, ipcRenderer);

  assert.ok(Array.isArray(preloadModule.DESKTOP_LOCAL_MODEL_PRESETS));
  assert.ok(preloadModule.DESKTOP_LOCAL_MODEL_PRESETS.length >= 1);
  for (const preset of preloadModule.DESKTOP_LOCAL_MODEL_PRESETS) {
    assert.equal(typeof preset.id, 'string');
    assert.match(preset.id, /^[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[a-z0-9]+(?:[._-][a-z0-9]+)*)?$/i);
    assert.equal(typeof preset.guidance, 'string');
  }
});

test('model preload fails closed for a malformed preset projection', (t) => {
  const ipcRenderer = {
    invoke: async () => undefined,
    on: () => undefined,
    removeListener: () => undefined,
  };
  const { preloadModule } = loadModelPreload(t, ipcRenderer, [{ id: '../invalid' }]);

  assert.deepEqual(preloadModule.DESKTOP_LOCAL_MODEL_PRESETS, []);
  assert.equal(Object.isFrozen(preloadModule.DESKTOP_LOCAL_MODEL_PRESETS), true);
});
