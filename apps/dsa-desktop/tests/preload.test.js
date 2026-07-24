const assert = require('node:assert/strict');
const test = require('node:test');
const Module = require('node:module');

test('preload exposes desktop version from BrowserWindow additionalArguments', (t) => {
  const originalLoad = Module._load;
  const originalArgv = [...process.argv];
  const exposeInMainWorldCalls = [];
  const expectedVersion = '3.12.0';
  const ipcRenderer = {
    invoke: () => Promise.resolve(),
    on: () => undefined,
    removeListener: () => undefined,
  };

  Module._load = function patchedLoad(request, parent, isMain) {
    if (request === 'electron') {
      return {
        contextBridge: {
          exposeInMainWorld: (...args) => {
            exposeInMainWorldCalls.push(args);
          },
        },
        ipcRenderer,
      };
    }
    return originalLoad.call(this, request, parent, isMain);
  };

  const preloadPath = require.resolve('../preload.js');
  delete require.cache[preloadPath];
  process.argv = [...originalArgv, `--dsa-desktop-version=${expectedVersion}`];

  t.after(() => {
    Module._load = originalLoad;
    process.argv = originalArgv;
    delete require.cache[preloadPath];
  });

  const preloadModule = require('../preload.js');

  assert.equal(exposeInMainWorldCalls.length, 2);
  const exposed = Object.fromEntries(exposeInMainWorldCalls);
  assert.deepEqual(Object.keys(exposed).sort(), ['dsaDesktop', 'stockPulseLocalModels']);
  assert.equal(exposed.dsaDesktop.version, expectedVersion);
  assert.equal(typeof exposed.dsaDesktop.getUpdateState, 'function');
  assert.equal(typeof exposed.dsaDesktop.checkForUpdates, 'function');
  assert.equal(typeof exposed.dsaDesktop.installDownloadedUpdate, 'function');
  assert.equal(typeof exposed.dsaDesktop.openReleasePage, 'function');
  assert.equal(typeof exposed.dsaDesktop.onUpdateStateChange, 'function');
  assert.deepEqual(Object.keys(exposed.stockPulseLocalModels).sort(), [
    'detect',
    'getState',
    'onStateChange',
    'openInstallGuide',
    'pull',
    'remove',
    'start',
    'stop',
  ]);
  assert.equal(
    preloadModule.readDesktopVersion([`--dsa-desktop-version=${expectedVersion}`]),
    expectedVersion
  );
});

test('preload falls back to empty version when BrowserWindow does not pass one', (t) => {
  const originalLoad = Module._load;
  const originalArgv = [...process.argv];
  const exposeInMainWorldCalls = [];
  const ipcRenderer = {
    invoke: () => Promise.resolve(),
    on: () => undefined,
    removeListener: () => undefined,
  };

  Module._load = function patchedLoad(request, parent, isMain) {
    if (request === 'electron') {
      return {
        contextBridge: {
          exposeInMainWorld: (...args) => {
            exposeInMainWorldCalls.push(args);
          },
        },
        ipcRenderer,
      };
    }
    return originalLoad.call(this, request, parent, isMain);
  };

  const preloadPath = require.resolve('../preload.js');
  delete require.cache[preloadPath];
  process.argv = originalArgv.filter((value) => !value.startsWith('--dsa-desktop-version='));

  t.after(() => {
    Module._load = originalLoad;
    process.argv = originalArgv;
    delete require.cache[preloadPath];
  });

  const preloadModule = require('../preload.js');

  assert.equal(exposeInMainWorldCalls.length, 2);
  assert.equal(exposeInMainWorldCalls[0][0], 'dsaDesktop');
  assert.equal(exposeInMainWorldCalls[0][1].version, '');
  assert.equal(exposeInMainWorldCalls[1][0], 'stockPulseLocalModels');
  assert.equal(preloadModule.readDesktopVersion(['--unrelated=1']), '');
});

test('createDesktopBridge delegates update actions to ipcRenderer', async (t) => {
  const originalLoad = Module._load;
  const listeners = new Map();
  const ipcRenderer = {
    invoke: async (channel, payload) => ({ channel, payload }),
    on: (channel, listener) => {
      listeners.set(channel, listener);
    },
    removeListener: (channel, listener) => {
      const current = listeners.get(channel);
      if (current === listener) {
        listeners.delete(channel);
      }
    },
  };

  const preloadPath = require.resolve('../preload.js');
  t.after(() => {
    Module._load = originalLoad;
    delete require.cache[preloadPath];
  });

  Module._load = function patchedLoad(request, parent, isMain) {
    if (request === 'electron') {
      return {
        contextBridge: {
          exposeInMainWorld: () => undefined,
        },
        ipcRenderer,
      };
    }
    return originalLoad.call(this, request, parent, isMain);
  };

  delete require.cache[preloadPath];
  const preloadModule = require('../preload.js');
  const desktopBridge = preloadModule.createDesktopBridge({
    version: '3.12.0',
    renderer: ipcRenderer,
  });

  assert.deepEqual(await desktopBridge.getUpdateState(), {
    channel: preloadModule.DESKTOP_GET_UPDATE_STATE_CHANNEL,
    payload: undefined,
  });
  assert.deepEqual(await desktopBridge.checkForUpdates(), {
    channel: preloadModule.DESKTOP_CHECK_FOR_UPDATES_CHANNEL,
    payload: undefined,
  });
  assert.deepEqual(await desktopBridge.installDownloadedUpdate(), {
    channel: preloadModule.DESKTOP_INSTALL_DOWNLOADED_UPDATE_CHANNEL,
    payload: undefined,
  });
  assert.deepEqual(await desktopBridge.openReleasePage('https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0'), {
    channel: preloadModule.DESKTOP_OPEN_RELEASE_PAGE_CHANNEL,
    payload: 'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0',
  });

  const receivedPayloads = [];
  const unsubscribe = desktopBridge.onUpdateStateChange((payload) => {
    receivedPayloads.push(payload);
  });
  listeners.get(preloadModule.DESKTOP_UPDATE_STATE_EVENT)(null, { status: 'update-available' });
  unsubscribe();

  assert.deepEqual(receivedPayloads, [{ status: 'update-available' }]);
  assert.equal(listeners.has(preloadModule.DESKTOP_UPDATE_STATE_EVENT), false);
});

test('createLocalModelBridge delegates lifecycle actions and removes state listeners', async (t) => {
  const originalLoad = Module._load;
  const listeners = new Map();
  const ipcRenderer = {
    invoke: async (channel, payload) => ({ channel, payload }),
    on: (channel, listener) => listeners.set(channel, listener),
    removeListener: (channel, listener) => {
      if (listeners.get(channel) === listener) listeners.delete(channel);
    },
  };
  const preloadPath = require.resolve('../preload.js');
  t.after(() => {
    Module._load = originalLoad;
    delete require.cache[preloadPath];
  });
  Module._load = function patchedLoad(request, parent, isMain) {
    if (request === 'electron') {
      return {
        contextBridge: { exposeInMainWorld: () => undefined },
        ipcRenderer,
      };
    }
    return originalLoad.call(this, request, parent, isMain);
  };
  delete require.cache[preloadPath];
  const preloadModule = require('../preload.js');
  const bridge = preloadModule.createLocalModelBridge({ renderer: ipcRenderer });

  for (const [method, channel] of [
    ['getState', preloadModule.DESKTOP_LOCAL_MODEL_GET_STATE_CHANNEL],
    ['detect', preloadModule.DESKTOP_LOCAL_MODEL_DETECT_CHANNEL],
    ['start', preloadModule.DESKTOP_LOCAL_MODEL_START_CHANNEL],
    ['stop', preloadModule.DESKTOP_LOCAL_MODEL_STOP_CHANNEL],
    ['openInstallGuide', preloadModule.DESKTOP_LOCAL_MODEL_OPEN_GUIDE_CHANNEL],
  ]) {
    assert.deepEqual(await bridge[method](), { channel, payload: undefined });
  }
  assert.deepEqual(await bridge.pull('qwen3:8b'), {
    channel: preloadModule.DESKTOP_LOCAL_MODEL_PULL_CHANNEL,
    payload: { modelId: 'qwen3:8b' },
  });
  assert.deepEqual(await bridge.remove('qwen3:8b'), {
    channel: preloadModule.DESKTOP_LOCAL_MODEL_REMOVE_CHANNEL,
    payload: { modelId: 'qwen3:8b' },
  });

  const states = [];
  const unsubscribe = bridge.onStateChange((state) => states.push(state));
  listeners.get(preloadModule.DESKTOP_LOCAL_MODEL_STATE_EVENT)(null, { status: 'running' });
  unsubscribe();
  assert.deepEqual(states, [{ status: 'running' }]);
  assert.equal(listeners.has(preloadModule.DESKTOP_LOCAL_MODEL_STATE_EVENT), false);
});
