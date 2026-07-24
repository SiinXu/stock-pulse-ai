const { contextBridge, ipcRenderer } = require('electron');

const DESKTOP_LOCAL_MODEL_GET_STATE_CHANNEL = 'desktop-local-model:get-state';
const DESKTOP_LOCAL_MODEL_DETECT_CHANNEL = 'desktop-local-model:detect';
const DESKTOP_LOCAL_MODEL_START_CHANNEL = 'desktop-local-model:start';
const DESKTOP_LOCAL_MODEL_STOP_CHANNEL = 'desktop-local-model:stop';
const DESKTOP_LOCAL_MODEL_PULL_CHANNEL = 'desktop-local-model:pull';
const DESKTOP_LOCAL_MODEL_REGISTER_CHANNEL = 'desktop-local-model:register';
const DESKTOP_LOCAL_MODEL_OPEN_GUIDE_CHANNEL = 'desktop-local-model:open-guide';
const DESKTOP_LOCAL_MODEL_STATE_EVENT = 'desktop-local-model:state';
const DESKTOP_LOCAL_MODEL_PRESETS_ARG_PREFIX = '--stockpulse-local-model-presets=';
const DESKTOP_LOCAL_MODEL_NAME_PATTERN =
  /^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:\/[a-z0-9]+(?:[._-][a-z0-9]+)*)?(?::[a-z0-9]+(?:[._-][a-z0-9]+)*)?$/i;

function readDesktopLocalModelPresets(argv = process.argv) {
  const rawArgument = argv.find((value) => (
    typeof value === 'string' && value.startsWith(DESKTOP_LOCAL_MODEL_PRESETS_ARG_PREFIX)
  ));
  if (!rawArgument) {
    return Object.freeze([]);
  }

  try {
    const encoded = rawArgument.slice(DESKTOP_LOCAL_MODEL_PRESETS_ARG_PREFIX.length);
    const parsed = JSON.parse(decodeURIComponent(encoded));
    if (!Array.isArray(parsed) || parsed.length === 0 || parsed.length > 32) {
      return Object.freeze([]);
    }
    const seen = new Set();
    const presets = parsed.map((preset) => {
      if (
        !preset ||
        typeof preset.id !== 'string' ||
        !DESKTOP_LOCAL_MODEL_NAME_PATTERN.test(preset.id) ||
        seen.has(preset.id) ||
        typeof preset.label !== 'string' ||
        typeof preset.guidance !== 'string' ||
        !Number.isFinite(preset.approxSizeGb) ||
        !Number.isInteger(preset.minRamGb)
      ) {
        throw new Error('invalid preset projection');
      }
      seen.add(preset.id);
      return Object.freeze({
        id: preset.id,
        label: preset.label,
        approxSizeGb: preset.approxSizeGb,
        minRamGb: preset.minRamGb,
        guidance: preset.guidance,
      });
    });
    return Object.freeze(presets);
  } catch (_error) {
    return Object.freeze([]);
  }
}

// The sandboxed preload receives inert catalog-derived metadata from main. It
// does not read files or perform network discovery.
const DESKTOP_LOCAL_MODEL_PRESETS = readDesktopLocalModelPresets();

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
  DESKTOP_LOCAL_MODEL_PRESETS_ARG_PREFIX,
  DESKTOP_LOCAL_MODEL_PRESETS,
  createLocalModelBridge,
  readDesktopLocalModelPresets,
};
