const assert = require('node:assert/strict');
const test = require('node:test');
const Module = require('node:module');

function loadAssistantPreload(t, ipcRenderer) {
  const originalLoad = Module._load;
  const exposed = [];
  const preloadPath = require.resolve('../assistant-preload.js');

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
    delete require.cache[preloadPath];
  });

  return {
    exposed,
    preloadModule: require('../assistant-preload.js'),
  };
}

test('assistant preload exposes only the minimal desktop assistant bridge', (t) => {
  const ipcRenderer = {
    invoke: async () => undefined,
    on: () => undefined,
    removeListener: () => undefined,
  };
  const { exposed } = loadAssistantPreload(t, ipcRenderer);

  assert.equal(exposed.length, 1);
  assert.equal(exposed[0][0], 'stockPulseAssistant');
  assert.deepEqual(Object.keys(exposed[0][1]).sort(), [
    'getState',
    'hide',
    'onStateChange',
    'openAction',
    'setMainWindowVisible',
  ]);
});

test('assistant bridge delegates structured actions and removes state listeners', async (t) => {
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
  const { preloadModule } = loadAssistantPreload(t, ipcRenderer);
  const bridge = preloadModule.createDesktopAssistantBridge({ renderer: ipcRenderer });

  assert.deepEqual(await bridge.getState(), {
    channel: preloadModule.DESKTOP_ASSISTANT_GET_STATE_CHANNEL,
    payload: undefined,
  });
  assert.deepEqual(await bridge.openAction('stock', 'AAPL'), {
    channel: preloadModule.DESKTOP_ASSISTANT_OPEN_ACTION_CHANNEL,
    payload: { action: 'stock', stockCode: 'AAPL' },
  });
  assert.deepEqual(await bridge.setMainWindowVisible(false), {
    channel: preloadModule.DESKTOP_ASSISTANT_SET_MAIN_VISIBILITY_CHANNEL,
    payload: false,
  });
  assert.deepEqual(await bridge.hide(), {
    channel: preloadModule.DESKTOP_ASSISTANT_HIDE_CHANNEL,
    payload: undefined,
  });

  const states = [];
  const unsubscribe = bridge.onStateChange((state) => states.push(state));
  listeners.get(preloadModule.DESKTOP_ASSISTANT_STATE_EVENT)(null, {
    serviceStatus: 'ready',
  });
  unsubscribe();

  assert.deepEqual(states, [{ serviceStatus: 'ready' }]);
  assert.equal(listeners.has(preloadModule.DESKTOP_ASSISTANT_STATE_EVENT), false);
  assert.equal(calls.length, 4);
});
