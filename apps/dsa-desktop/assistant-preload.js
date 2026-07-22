const { contextBridge, ipcRenderer } = require('electron');

const DESKTOP_ASSISTANT_GET_STATE_CHANNEL = 'desktop-assistant:get-state';
const DESKTOP_ASSISTANT_OPEN_ACTION_CHANNEL = 'desktop-assistant:open-action';
const DESKTOP_ASSISTANT_SET_MAIN_VISIBILITY_CHANNEL = 'desktop-assistant:set-main-visibility';
const DESKTOP_ASSISTANT_HIDE_CHANNEL = 'desktop-assistant:hide';
const DESKTOP_ASSISTANT_STATE_EVENT = 'desktop-assistant:state';

function createDesktopAssistantBridge({ renderer = ipcRenderer } = {}) {
  return {
    getState() {
      return renderer.invoke(DESKTOP_ASSISTANT_GET_STATE_CHANNEL);
    },
    openAction(action, stockCode = '') {
      return renderer.invoke(DESKTOP_ASSISTANT_OPEN_ACTION_CHANNEL, { action, stockCode });
    },
    setMainWindowVisible(visible) {
      return renderer.invoke(DESKTOP_ASSISTANT_SET_MAIN_VISIBILITY_CHANNEL, visible);
    },
    hide() {
      return renderer.invoke(DESKTOP_ASSISTANT_HIDE_CHANNEL);
    },
    onStateChange(listener) {
      if (typeof listener !== 'function') {
        return () => undefined;
      }
      const handler = (_event, payload) => listener(payload);
      renderer.on(DESKTOP_ASSISTANT_STATE_EVENT, handler);
      return () => renderer.removeListener(DESKTOP_ASSISTANT_STATE_EVENT, handler);
    },
  };
}

contextBridge.exposeInMainWorld(
  'stockPulseAssistant',
  createDesktopAssistantBridge()
);

module.exports = {
  DESKTOP_ASSISTANT_GET_STATE_CHANNEL,
  DESKTOP_ASSISTANT_HIDE_CHANNEL,
  DESKTOP_ASSISTANT_OPEN_ACTION_CHANNEL,
  DESKTOP_ASSISTANT_SET_MAIN_VISIBILITY_CHANNEL,
  DESKTOP_ASSISTANT_STATE_EVENT,
  createDesktopAssistantBridge,
};
