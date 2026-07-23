const { contextBridge, ipcRenderer } = require('electron');

const DESKTOP_LOCAL_MODEL_GET_STATE_CHANNEL = 'desktop-local-model:get-state';
const DESKTOP_LOCAL_MODEL_DETECT_CHANNEL = 'desktop-local-model:detect';
const DESKTOP_LOCAL_MODEL_START_CHANNEL = 'desktop-local-model:start';
const DESKTOP_LOCAL_MODEL_STOP_CHANNEL = 'desktop-local-model:stop';
const DESKTOP_LOCAL_MODEL_PULL_CHANNEL = 'desktop-local-model:pull';
const DESKTOP_LOCAL_MODEL_REGISTER_CHANNEL = 'desktop-local-model:register';
const DESKTOP_LOCAL_MODEL_OPEN_GUIDE_CHANNEL = 'desktop-local-model:open-guide';
const DESKTOP_LOCAL_MODEL_STATE_EVENT = 'desktop-local-model:state';

// The recommended presets are duplicated here as inert display metadata so the
// isolated renderer never has to reach the network. The main process remains
// the single source of truth for which ids may actually be pulled.
const DESKTOP_LOCAL_MODEL_PRESETS = Object.freeze([
  Object.freeze({
    id: 'llama3.2:3b',
    label: 'Llama 3.2 3B',
    approxSizeGb: 2.0,
    minRamGb: 8,
    guidance: 'Lightweight general model. Runs on 8 GB RAM machines.',
  }),
  Object.freeze({
    id: 'qwen3:4b',
    label: 'Qwen3 4B',
    approxSizeGb: 2.6,
    minRamGb: 8,
    guidance: 'Compact reasoning model. Comfortable on 8-16 GB RAM.',
  }),
  Object.freeze({
    id: 'qwen3:8b',
    label: 'Qwen3 8B',
    approxSizeGb: 5.2,
    minRamGb: 16,
    guidance: 'Balanced quality for 16 GB RAM or more.',
  }),
]);

function createLocalModelBridge({ renderer = ipcRenderer } = {}) {
  return {
    presets: DESKTOP_LOCAL_MODEL_PRESETS,
    getState() {
      return renderer.invoke(DESKTOP_LOCAL_MODEL_GET_STATE_CHANNEL);
    },
    detect() {
      return renderer.invoke(DESKTOP_LOCAL_MODEL_DETECT_CHANNEL);
    },
    start() {
      return renderer.invoke(DESKTOP_LOCAL_MODEL_START_CHANNEL);
    },
    stop() {
      return renderer.invoke(DESKTOP_LOCAL_MODEL_STOP_CHANNEL);
    },
    pull(modelId) {
      return renderer.invoke(DESKTOP_LOCAL_MODEL_PULL_CHANNEL, { modelId });
    },
    register(modelId) {
      return renderer.invoke(DESKTOP_LOCAL_MODEL_REGISTER_CHANNEL, { modelId });
    },
    openInstallGuide() {
      return renderer.invoke(DESKTOP_LOCAL_MODEL_OPEN_GUIDE_CHANNEL);
    },
    onStateChange(listener) {
      if (typeof listener !== 'function') {
        return () => undefined;
      }
      const handler = (_event, payload) => listener(payload);
      renderer.on(DESKTOP_LOCAL_MODEL_STATE_EVENT, handler);
      return () => renderer.removeListener(DESKTOP_LOCAL_MODEL_STATE_EVENT, handler);
    },
  };
}

contextBridge.exposeInMainWorld('stockPulseLocalModels', createLocalModelBridge());

module.exports = {
  DESKTOP_LOCAL_MODEL_GET_STATE_CHANNEL,
  DESKTOP_LOCAL_MODEL_DETECT_CHANNEL,
  DESKTOP_LOCAL_MODEL_START_CHANNEL,
  DESKTOP_LOCAL_MODEL_STOP_CHANNEL,
  DESKTOP_LOCAL_MODEL_PULL_CHANNEL,
  DESKTOP_LOCAL_MODEL_REGISTER_CHANNEL,
  DESKTOP_LOCAL_MODEL_OPEN_GUIDE_CHANNEL,
  DESKTOP_LOCAL_MODEL_STATE_EVENT,
  DESKTOP_LOCAL_MODEL_PRESETS,
  createLocalModelBridge,
};
