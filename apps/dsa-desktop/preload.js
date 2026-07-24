const { contextBridge, ipcRenderer } = require('electron');

const DESKTOP_VERSION_ARG_PREFIX = '--dsa-desktop-version=';
const DESKTOP_GET_UPDATE_STATE_CHANNEL = 'desktop:get-update-state';
const DESKTOP_CHECK_FOR_UPDATES_CHANNEL = 'desktop:check-for-updates';
const DESKTOP_INSTALL_DOWNLOADED_UPDATE_CHANNEL = 'desktop:install-downloaded-update';
const DESKTOP_OPEN_RELEASE_PAGE_CHANNEL = 'desktop:open-release-page';
const DESKTOP_UPDATE_STATE_EVENT = 'desktop:update-state';
const DESKTOP_LOCAL_MODEL_GET_STATE_CHANNEL = 'desktop-local-model:get-state';
const DESKTOP_LOCAL_MODEL_DETECT_CHANNEL = 'desktop-local-model:detect';
const DESKTOP_LOCAL_MODEL_START_CHANNEL = 'desktop-local-model:start';
const DESKTOP_LOCAL_MODEL_STOP_CHANNEL = 'desktop-local-model:stop';
const DESKTOP_LOCAL_MODEL_PULL_CHANNEL = 'desktop-local-model:pull';
const DESKTOP_LOCAL_MODEL_REMOVE_CHANNEL = 'desktop-local-model:remove';
const DESKTOP_LOCAL_MODEL_OPEN_GUIDE_CHANNEL = 'desktop-local-model:open-guide';
const DESKTOP_LOCAL_MODEL_STATE_EVENT = 'desktop-local-model:state';

function readDesktopVersion(argv = process.argv) {
  const versionArg = argv.find(
    (value) => typeof value === 'string' && value.startsWith(DESKTOP_VERSION_ARG_PREFIX)
  );
  return versionArg ? versionArg.slice(DESKTOP_VERSION_ARG_PREFIX.length) : '';
}

function createDesktopBridge({
  version = readDesktopVersion(),
  renderer = ipcRenderer,
} = {}) {
  return {
    version,
    getUpdateState() {
      return renderer.invoke(DESKTOP_GET_UPDATE_STATE_CHANNEL);
    },
    checkForUpdates() {
      return renderer.invoke(DESKTOP_CHECK_FOR_UPDATES_CHANNEL);
    },
    installDownloadedUpdate() {
      return renderer.invoke(DESKTOP_INSTALL_DOWNLOADED_UPDATE_CHANNEL);
    },
    openReleasePage(releaseUrl) {
      return renderer.invoke(DESKTOP_OPEN_RELEASE_PAGE_CHANNEL, releaseUrl);
    },
    onUpdateStateChange(listener) {
      if (typeof listener !== 'function') {
        return () => undefined;
      }

      const handler = (_event, payload) => {
        listener(payload);
      };
      renderer.on(DESKTOP_UPDATE_STATE_EVENT, handler);
      return () => {
        renderer.removeListener(DESKTOP_UPDATE_STATE_EVENT, handler);
      };
    },
  };
}

function createLocalModelBridge({ renderer = ipcRenderer } = {}) {
  return {
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
    remove(modelId, expectedBaseUrl) {
      return renderer.invoke(DESKTOP_LOCAL_MODEL_REMOVE_CHANNEL, {
        modelId,
        expectedBaseUrl,
      });
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

contextBridge.exposeInMainWorld('dsaDesktop', createDesktopBridge());
contextBridge.exposeInMainWorld('stockPulseLocalModels', createLocalModelBridge());

module.exports = {
  DESKTOP_CHECK_FOR_UPDATES_CHANNEL,
  DESKTOP_GET_UPDATE_STATE_CHANNEL,
  DESKTOP_INSTALL_DOWNLOADED_UPDATE_CHANNEL,
  DESKTOP_OPEN_RELEASE_PAGE_CHANNEL,
  DESKTOP_UPDATE_STATE_EVENT,
  DESKTOP_VERSION_ARG_PREFIX,
  DESKTOP_LOCAL_MODEL_GET_STATE_CHANNEL,
  DESKTOP_LOCAL_MODEL_DETECT_CHANNEL,
  DESKTOP_LOCAL_MODEL_START_CHANNEL,
  DESKTOP_LOCAL_MODEL_STOP_CHANNEL,
  DESKTOP_LOCAL_MODEL_PULL_CHANNEL,
  DESKTOP_LOCAL_MODEL_REMOVE_CHANNEL,
  DESKTOP_LOCAL_MODEL_OPEN_GUIDE_CHANNEL,
  DESKTOP_LOCAL_MODEL_STATE_EVENT,
  createDesktopBridge,
  createLocalModelBridge,
  readDesktopVersion,
};
