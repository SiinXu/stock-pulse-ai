const assert = require('node:assert/strict');
const test = require('node:test');
const Module = require('node:module');
const { EventEmitter } = require('node:events');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const POSIX_PATH_DELIMITER = ':';

function loadMainModule(t, options = {}) {
  const originalLoad = Module._load;
  const originalPlatform = Object.getOwnPropertyDescriptor(process, 'platform');
  const ipcMainHandlers = new Map();
  const fakeApp = {
    isPackaged: false,
    getVersion: () => '3.12.0',
    getPath: () => '/tmp/dsa-user-data',
    requestSingleInstanceLock: () => true,
    setAsDefaultProtocolClient: () => true,
    whenReady: () => ({ then: () => undefined }),
    on: () => undefined,
    quit: () => undefined,
    ...(options.app || {}),
  };
  const fakeDialog = {
    showMessageBox: async () => ({ response: 0 }),
    ...(options.dialog || {}),
  };
  const fakeShell = {
    openExternal: async () => true,
  };
  const fakeIpcMain = {
    handle: (channel, handler) => {
      ipcMainHandlers.set(channel, handler);
    },
  };
  function defaultBrowserWindow() {
    return {
      isDestroyed: () => false,
      getAllWindows: () => [],
      setBackgroundColor: () => undefined,
      once: () => undefined,
      webContents: {
        on: () => undefined,
        send: () => undefined,
        setWindowOpenHandler: () => undefined,
      },
      loadFile: async () => undefined,
      loadURL: async () => undefined,
    };
  }
  defaultBrowserWindow.getAllWindows = () => [];
  const fakeBrowserWindow = options.browserWindow || defaultBrowserWindow;
  const fakeNativeTheme = {
    shouldUseDarkColors: false,
    on: () => undefined,
    removeListener: () => undefined,
  };
  const fakeMenu = options.menu || {
    buildFromTemplate: (template) => ({ template }),
  };
  const fakeNativeImage = options.nativeImage || {
    createFromPath: () => ({ isEmpty: () => false }),
  };
  class DefaultTray extends EventEmitter {
    isDestroyed() {
      return false;
    }

    setToolTip() {}

    setContextMenu() {}
  }
  const fakeTray = options.tray || DefaultTray;

  Module._load = function patchedLoad(request, parent, isMain) {
    if (request === 'electron') {
      return {
        app: fakeApp,
        BrowserWindow: fakeBrowserWindow,
        dialog: fakeDialog,
        ipcMain: fakeIpcMain,
        Menu: fakeMenu,
        nativeImage: fakeNativeImage,
        shell: fakeShell,
        nativeTheme: fakeNativeTheme,
        Tray: fakeTray,
      };
    }
    if (request === 'http' && options.http) {
      return options.http;
    }
    if (request === 'net' && options.net) {
      return options.net;
    }
    if (request === 'child_process' && options.childProcess) {
      return options.childProcess;
    }
    if (request === 'electron-updater' && options.electronUpdater) {
      return {
        autoUpdater: options.electronUpdater,
      };
    }
    return originalLoad.call(this, request, parent, isMain);
  };

  const mainPath = require.resolve('../main.js');
  delete require.cache[mainPath];

  t.after(() => {
    Module._load = originalLoad;
    if (options.platform && originalPlatform) {
      Object.defineProperty(process, 'platform', originalPlatform);
    }
    delete require.cache[mainPath];
  });

  if (options.platform) {
    Object.defineProperty(process, 'platform', { ...originalPlatform, value: options.platform });
  }

  const mainModule = require('../main.js');
  mainModule.__getIpcMainHandler = (channel) => ipcMainHandlers.get(channel);
  return mainModule;
}

test('parseSemver accepts stable and prerelease tags', (t) => {
  const mainModule = loadMainModule(t);

  assert.deepEqual(mainModule.parseSemver('v3.13.0-beta.2'), {
    major: 3,
    minor: 13,
    patch: 0,
    prerelease: ['beta', '2'],
  });
  assert.equal(mainModule.parseSemver('nightly-20260425'), null);
});

test('compareVersions follows semantic version ordering', (t) => {
  const mainModule = loadMainModule(t);

  assert.equal(mainModule.compareVersions('3.12.0', '3.13.0'), -1);
  assert.equal(mainModule.compareVersions('v3.13.0', '3.13.0'), 0);
  assert.equal(mainModule.compareVersions('3.13.0', '3.13.0-beta.1'), 1);
  assert.equal(mainModule.compareVersions('3.13.0-beta.2', '3.13.0-beta.10'), -1);
});

test('desktop package exposes StockPulse while retaining the stable upgrade appId', () => {
  const repositoryRoot = path.resolve(__dirname, '..', '..', '..');
  const packageMetadata = JSON.parse(
    fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf-8')
  );
  const loadingPage = fs.readFileSync(
    path.join(__dirname, '..', 'renderer', 'loading.html'),
    'utf-8'
  );
  const releaseWorkflow = fs.readFileSync(
    path.join(repositoryRoot, '.github', 'workflows', 'desktop-release.yml'),
    'utf-8'
  );
  const updaterVerification = fs.readFileSync(
    path.join(repositoryRoot, 'scripts', 'verify-desktop-updater-artifacts.ps1'),
    'utf-8'
  );
  const installerScript = fs.readFileSync(
    path.join(__dirname, '..', 'installer.nsh'),
    'utf-8'
  );

  assert.equal(packageMetadata.name, 'stockpulse-desktop');
  assert.equal(packageMetadata.build.productName, 'StockPulse');
  assert.equal(packageMetadata.build.appId, 'com.daily-stock-analysis.desktop');
  assert.deepEqual(packageMetadata.build.protocols, [
    {
      name: 'StockPulse',
      schemes: ['stockpulse'],
    },
  ]);
  assert.equal(
    packageMetadata.build.win.artifactName,
    'stockpulse-windows-installer-v${version}.${ext}'
  );
  assert.match(loadingPage, /<title>StockPulse<\/title>/);
  assert.match(loadingPage, /<h1 class="title">StockPulse<\/h1>/);
  assert.doesNotMatch(loadingPage, /Daily Stock Analysis/);
  assert.match(releaseWorkflow, /stockpulse-windows-installer-/);
  assert.match(releaseWorkflow, /stockpulse-windows-noinstall-/);
  assert.match(releaseWorkflow, /stockpulse-macos-/);
  assert.match(releaseWorkflow, /lib\/ollama\/llama-server\.exe/);
  assert.match(releaseWorkflow, /Resources\/ollama\/llama-server/);
  assert.equal((releaseWorkflow.match(/verifyPreparedOllama/g) || []).length, 2);
  assert.match(updaterVerification, /stockpulse-windows-installer-/);
  assert.match(installerScript, /!macro customInstall\b/);
  assert.match(installerScript, /Software\\Classes\\stockpulse\\shell\\open\\command/);
  assert.match(installerScript, /'"\$appExe" "%1"'/);
  assert.match(installerScript, /!macro customUnInstall\b/);
  assert.match(installerScript, /DeleteRegKey SHELL_CONTEXT "Software\\Classes\\stockpulse"/);
});

test('desktop package includes the isolated floating assistant surface and tray asset', () => {
  const packageMetadata = JSON.parse(
    fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf-8')
  );
  const assistantPage = fs.readFileSync(
    path.join(__dirname, '..', 'renderer', 'assistant.html'),
    'utf-8'
  );
  const assistantScript = fs.readFileSync(
    path.join(__dirname, '..', 'renderer', 'assistant.js'),
    'utf-8'
  );

  assert.ok(packageMetadata.build.files.includes('assistant-preload.js'));
  assert.ok(packageMetadata.build.files.includes('renderer/**/*'));
  assert.ok(packageMetadata.build.extraResources.some((entry) =>
    entry.to === 'assistant-tray.png'
    && entry.from.endsWith('lightlogo.iconset/icon_32x32.png')));
  assert.match(assistantPage, /connect-src 'none'/);
  assert.match(assistantPage, /script-src 'self'/);
  assert.match(assistantPage, /id="stockLookupForm"/);
  assert.match(assistantPage, /data-action="analysis"/);
  assert.doesNotMatch(assistantScript, /\bfetch\s*\(/);
  assert.doesNotMatch(assistantScript, /innerHTML/);
});

test('desktop assistant actions map only to allowlisted routes', (t) => {
  const mainModule = loadMainModule(t);

  assert.equal(mainModule.buildDesktopAssistantRoute('analysis'), '/');
  assert.equal(mainModule.buildDesktopAssistantRoute('portfolio'), '/portfolio');
  assert.equal(mainModule.buildDesktopAssistantRoute('alerts'), '/alerts');
  assert.equal(mainModule.buildDesktopAssistantRoute('screening'), '/screening');
  assert.equal(mainModule.buildDesktopAssistantRoute('stock', ' aapl '), '/stocks/AAPL');
  assert.equal(mainModule.buildDesktopAssistantRoute('stock', 'HK00700'), '/stocks/HK00700');

  for (const [action, stockCode] of [
    ['settings', ''],
    ['stock', 'AAPL/../../settings'],
    ['stock', 'AAPL%2Fsettings'],
    ['stock', 'AAPL?next=https://evil.example'],
    ['stock', ''],
    ['stock', 'X'.repeat(17)],
  ]) {
    assert.equal(mainModule.buildDesktopAssistantRoute(action, stockCode), null);
  }
});

test('desktop assistant reports only shell-owned readiness states', (t) => {
  const mainModule = loadMainModule(t);

  assert.deepEqual(mainModule.buildDesktopAssistantState(), {
    serviceStatus: 'starting',
    mainWindowVisible: false,
    lastReadyAt: '',
  });

  mainModule.__setDesktopAssistantStateForTest({
    webReady: true,
    lastReadyAt: '2026-07-22T08:00:00.000Z',
  });
  assert.deepEqual(mainModule.buildDesktopAssistantState(), {
    serviceStatus: 'ready',
    mainWindowVisible: false,
    lastReadyAt: '2026-07-22T08:00:00.000Z',
  });

  mainModule.__setDesktopAssistantStateForTest({
    webReady: false,
    startError: new Error('backend stopped'),
    lastReadyAt: '2026-07-22T08:00:00.000Z',
  });
  assert.deepEqual(mainModule.buildDesktopAssistantState(), {
    serviceStatus: 'unavailable',
    mainWindowVisible: false,
    lastReadyAt: '2026-07-22T08:00:00.000Z',
  });
});

test('floating assistant BrowserWindow is fixed, isolated, and hides instead of closing', async (t) => {
  const mainModule = loadMainModule(t);
  let browserWindowOptions = null;
  let loadedPath = '';
  let openHandler = null;
  const navigationHandlers = new Map();
  let hidden = false;
  let centered = false;

  class FakeAssistantWindow extends EventEmitter {
    constructor(options) {
      super();
      browserWindowOptions = options;
      this.webContents = {
        send: () => undefined,
        on: (eventName, handler) => {
          navigationHandlers.set(eventName, handler);
        },
        setWindowOpenHandler: (handler) => {
          openHandler = handler;
        },
      };
    }

    isDestroyed() {
      return false;
    }

    async loadFile(filePath) {
      loadedPath = filePath;
    }

    hide() {
      hidden = true;
    }

    center() {
      centered = true;
    }
  }

  const assistant = await mainModule.createDesktopAssistantWindow({
    BrowserWindowClass: FakeAssistantWindow,
  });

  assert.equal(browserWindowOptions.frame, false);
  assert.equal(browserWindowOptions.alwaysOnTop, true);
  assert.equal(browserWindowOptions.resizable, false);
  assert.equal(browserWindowOptions.skipTaskbar, true);
  assert.equal(browserWindowOptions.webPreferences.nodeIntegration, false);
  assert.equal(browserWindowOptions.webPreferences.contextIsolation, true);
  assert.equal(browserWindowOptions.webPreferences.sandbox, true);
  assert.match(browserWindowOptions.webPreferences.preload, /assistant-preload\.js$/);
  assert.match(loadedPath, /renderer\/assistant\.html$/);
  assert.deepEqual(openHandler({ url: 'https://evil.example' }), { action: 'deny' });
  for (const eventName of ['will-navigate', 'will-redirect']) {
    assert.equal(typeof navigationHandlers.get(eventName), 'function', eventName);
    let navigationPrevented = false;
    navigationHandlers.get(eventName)({
      preventDefault: () => {
        navigationPrevented = true;
      },
    }, 'https://evil.example');
    assert.equal(navigationPrevented, true, eventName);
  }
  assert.equal(centered, true);

  let prevented = false;
  assistant.emit('close', {
    preventDefault: () => {
      prevented = true;
    },
  });
  assert.equal(prevented, true);
  assert.equal(hidden, true);
});

test('desktop assistant IPC rejects other renderers and routes validated stock actions', async (t) => {
  const mainModule = loadMainModule(t);
  const assistantWebContents = {
    send: () => undefined,
  };
  let assistantHidden = false;
  const assistantWindowRef = {
    isDestroyed: () => false,
    hide: () => {
      assistantHidden = true;
    },
    webContents: assistantWebContents,
  };
  const lifecycle = [];
  const mainWindowRef = {
    isDestroyed: () => false,
    isMinimized: () => false,
    isVisible: () => true,
    show: () => lifecycle.push('show'),
    focus: () => lifecycle.push('focus'),
    loadURL: async (url) => lifecycle.push(`load:${url}`),
  };
  mainModule.__setAssistantWindowForTest(assistantWindowRef);
  mainModule.__setMainWindowForTest(mainWindowRef);
  mainModule.__setDesktopDeepLinkStateForTest({
    mainPageUrl: 'http://127.0.0.1:8123/?desktop_version=3.21.0&cache_bust=123',
    ready: true,
  });

  const openAction = mainModule.__getIpcMainHandler(
    mainModule.DESKTOP_ASSISTANT_OPEN_ACTION_CHANNEL
  );
  await assert.rejects(
    () => openAction({ sender: {} }, { action: 'portfolio' }),
    /Unauthorized desktop assistant IPC sender/
  );

  assert.deepEqual(
    await openAction(
      { sender: assistantWebContents },
      { action: 'stock', stockCode: 'aapl' }
    ),
    { ok: true, pending: false }
  );
  assert.deepEqual(lifecycle.slice(0, 2), ['show', 'focus']);
  assert.equal(new URL(lifecycle[2].slice('load:'.length)).pathname, '/stocks/AAPL');
  assert.equal(assistantHidden, true);

  const loadCount = lifecycle.filter((entry) => entry.startsWith('load:')).length;
  assert.deepEqual(
    await openAction(
      { sender: assistantWebContents },
      { action: 'stock', stockCode: 'AAPL/../../settings' }
    ),
    { ok: false, error: 'invalid-action' }
  );
  assert.equal(lifecycle.filter((entry) => entry.startsWith('load:')).length, loadCount);
});

test('desktop assistant stays visible when a validated shortcut cannot navigate', async (t) => {
  const mainModule = loadMainModule(t);
  const assistantWebContents = {
    send: () => undefined,
  };
  let assistantHidden = false;
  mainModule.__setAssistantWindowForTest({
    isDestroyed: () => false,
    hide: () => {
      assistantHidden = true;
    },
    webContents: assistantWebContents,
  });
  mainModule.__setMainWindowForTest({
    isDestroyed: () => false,
    isMinimized: () => false,
    isVisible: () => true,
    show: () => undefined,
    focus: () => undefined,
    loadURL: async () => {
      throw new Error('navigation failed');
    },
  });
  mainModule.__setDesktopDeepLinkStateForTest({
    mainPageUrl: 'http://127.0.0.1:8123/?desktop_version=3.21.0&cache_bust=123',
    ready: true,
  });

  const openAction = mainModule.__getIpcMainHandler(
    mainModule.DESKTOP_ASSISTANT_OPEN_ACTION_CHANNEL
  );
  assert.deepEqual(
    await openAction({ sender: assistantWebContents }, { action: 'portfolio' }),
    { ok: false, error: 'navigation-failed' }
  );
  assert.equal(assistantHidden, false);
});

test('desktop assistant preserves navigation failure when readiness drops during load', async (t) => {
  const mainModule = loadMainModule(t);
  const assistantWebContents = {
    send: () => undefined,
  };
  let assistantHidden = false;
  let rejectNavigation = null;
  let markNavigationStarted = null;
  const navigationStarted = new Promise((resolve) => {
    markNavigationStarted = resolve;
  });
  mainModule.__setAssistantWindowForTest({
    isDestroyed: () => false,
    hide: () => {
      assistantHidden = true;
    },
    webContents: assistantWebContents,
  });
  mainModule.__setMainWindowForTest({
    isDestroyed: () => false,
    isMinimized: () => false,
    isVisible: () => true,
    show: () => undefined,
    focus: () => undefined,
    loadURL: () => new Promise((_resolve, reject) => {
      rejectNavigation = reject;
      markNavigationStarted();
    }),
  });
  mainModule.__setDesktopDeepLinkStateForTest({
    mainPageUrl: 'http://127.0.0.1:8123/?desktop_version=3.21.0&cache_bust=123',
    ready: true,
  });

  const openAction = mainModule.__getIpcMainHandler(
    mainModule.DESKTOP_ASSISTANT_OPEN_ACTION_CHANNEL
  );
  const actionResult = openAction(
    { sender: assistantWebContents },
    { action: 'portfolio' }
  );
  await navigationStarted;
  assert.equal(typeof rejectNavigation, 'function');
  mainModule.__setDesktopAssistantStateForTest({
    webReady: false,
    startError: new Error('backend exited'),
  });
  rejectNavigation(new Error('navigation failed'));

  assert.deepEqual(await actionResult, { ok: false, error: 'navigation-failed' });
  assert.equal(mainModule.__getPendingDesktopDeepLinkRouteForTest(), null);
  assert.equal(assistantHidden, false);
});

test('desktop assistant observes failure when queued behind an active OS navigation', async (t) => {
  const mainModule = loadMainModule(t);
  const assistantWebContents = {
    send: () => undefined,
  };
  let assistantHidden = false;
  const navigationAttempts = [];
  let markFirstNavigationStarted = null;
  const firstNavigationStarted = new Promise((resolve) => {
    markFirstNavigationStarted = resolve;
  });
  let markSecondNavigationStarted = null;
  const secondNavigationStarted = new Promise((resolve) => {
    markSecondNavigationStarted = resolve;
  });
  mainModule.__setAssistantWindowForTest({
    isDestroyed: () => false,
    hide: () => {
      assistantHidden = true;
    },
    webContents: assistantWebContents,
  });
  mainModule.__setMainWindowForTest({
    isDestroyed: () => false,
    isMinimized: () => false,
    isVisible: () => true,
    show: () => undefined,
    focus: () => undefined,
    loadURL: (url) => new Promise((resolve, reject) => {
      navigationAttempts.push({ url, resolve, reject });
      if (navigationAttempts.length === 1) {
        markFirstNavigationStarted();
      }
      if (navigationAttempts.length === 2) {
        markSecondNavigationStarted();
      }
    }),
  });
  mainModule.__setDesktopDeepLinkStateForTest({
    mainPageUrl: 'http://127.0.0.1:8123/?desktop_version=3.21.0&cache_bust=123',
    ready: true,
  });

  assert.equal(mainModule.queueDesktopDeepLink('stockpulse://app/stocks/MSFT'), true);
  const osNavigation = mainModule.flushPendingDesktopDeepLink();
  await firstNavigationStarted;
  assert.equal(navigationAttempts.length, 1);

  const openAction = mainModule.__getIpcMainHandler(
    mainModule.DESKTOP_ASSISTANT_OPEN_ACTION_CHANNEL
  );
  const actionResult = openAction(
    { sender: assistantWebContents },
    { action: 'portfolio' }
  );
  assert.equal(navigationAttempts.length, 1);

  navigationAttempts[0].resolve();
  await secondNavigationStarted;
  assert.equal(new URL(navigationAttempts[1].url).pathname, '/portfolio');
  navigationAttempts[1].reject(new Error('navigation failed'));

  assert.equal(await osNavigation, true);
  assert.deepEqual(await actionResult, { ok: false, error: 'navigation-failed' });
  assert.equal(mainModule.__getPendingDesktopDeepLinkRouteForTest(), null);
  assert.equal(assistantHidden, false);
});

test('desktop assistant stays visible when a queued route remains pending after readiness loss', async (t) => {
  const mainModule = loadMainModule(t);
  const assistantWebContents = {
    send: () => undefined,
  };
  let assistantHidden = false;
  let resolveOsNavigation = null;
  let markOsNavigationStarted = null;
  const osNavigationStarted = new Promise((resolve) => {
    markOsNavigationStarted = resolve;
  });
  mainModule.__setAssistantWindowForTest({
    isDestroyed: () => false,
    hide: () => {
      assistantHidden = true;
    },
    webContents: assistantWebContents,
  });
  mainModule.__setMainWindowForTest({
    isDestroyed: () => false,
    isMinimized: () => false,
    isVisible: () => true,
    show: () => undefined,
    focus: () => undefined,
    loadURL: () => new Promise((resolve) => {
      resolveOsNavigation = resolve;
      markOsNavigationStarted();
    }),
  });
  mainModule.__setDesktopDeepLinkStateForTest({
    mainPageUrl: 'http://127.0.0.1:8123/?desktop_version=3.21.0&cache_bust=123',
    ready: true,
  });

  assert.equal(mainModule.queueDesktopDeepLink('stockpulse://app/stocks/MSFT'), true);
  const osNavigation = mainModule.flushPendingDesktopDeepLink();
  await osNavigationStarted;
  const openAction = mainModule.__getIpcMainHandler(
    mainModule.DESKTOP_ASSISTANT_OPEN_ACTION_CHANNEL
  );
  const actionResult = openAction(
    { sender: assistantWebContents },
    { action: 'portfolio' }
  );

  mainModule.__setDesktopAssistantStateForTest({
    webReady: false,
    startError: new Error('backend exited'),
  });
  resolveOsNavigation();

  assert.equal(await osNavigation, true);
  assert.deepEqual(await actionResult, { ok: true, pending: true });
  assert.equal(mainModule.__getPendingDesktopDeepLinkRouteForTest(), '/portfolio');
  assert.equal(assistantHidden, false);
});

test('older deep-link flush cleanup cannot deregister a newer flush generation', async (t) => {
  const mainModule = loadMainModule(t);
  const navigationAttempts = [];
  let markThirdNavigationStarted = null;
  const thirdNavigationStarted = new Promise((resolve) => {
    markThirdNavigationStarted = resolve;
  });
  mainModule.__setMainWindowForTest({
    isDestroyed: () => false,
    loadURL: (url) => new Promise((resolve) => {
      navigationAttempts.push({ url, resolve });
      if (navigationAttempts.length === 3) {
        markThirdNavigationStarted();
      }
    }),
  });
  mainModule.__setDesktopDeepLinkStateForTest({
    mainPageUrl: 'http://127.0.0.1:8123/?desktop_version=3.21.0&cache_bust=123',
    ready: true,
    pendingRoute: '/stocks/MSFT',
  });
  const firstFlush = mainModule.flushPendingDesktopDeepLink();
  await Promise.resolve();
  assert.equal(navigationAttempts.length, 1);

  mainModule.__setDesktopDeepLinkStateForTest({
    mainPageUrl: 'http://127.0.0.1:8123/?desktop_version=3.21.0&cache_bust=456',
    ready: true,
    pendingRoute: '/alerts',
  });
  const secondFlush = mainModule.flushPendingDesktopDeepLink();
  await Promise.resolve();
  assert.equal(navigationAttempts.length, 2);

  navigationAttempts[0].resolve();
  await firstFlush;
  assert.equal(mainModule.queueDesktopDeepLink('stockpulse://app/screening'), true);
  const joinedFlush = mainModule.flushPendingDesktopDeepLink();
  await Promise.resolve();
  assert.equal(navigationAttempts.length, 2);

  navigationAttempts[1].resolve();
  await thirdNavigationStarted;
  assert.equal(new URL(navigationAttempts[2].url).pathname, '/screening');
  navigationAttempts[2].resolve();
  assert.equal(await secondFlush, true);
  assert.equal(await joinedFlush, true);
});

test('desktop tray opens the unified local model Settings panel', async (t) => {
  const mainModule = loadMainModule(t);
  let resolvedIconPath = '';
  let menuTemplate = null;

  class FakeTray extends EventEmitter {
    constructor(icon) {
      super();
      this.icon = icon;
      this.destroyed = false;
    }

    isDestroyed() {
      return this.destroyed;
    }

    setToolTip(value) {
      this.toolTip = value;
    }

    setContextMenu(value) {
      this.contextMenu = value;
    }
  }

  const tray = mainModule.createDesktopTray({
    iconPath: '/tmp/assistant-tray.png',
    TrayClass: FakeTray,
    imageApi: {
      createFromPath: (iconPath) => {
        resolvedIconPath = iconPath;
        return { isEmpty: () => false };
      },
    },
    menuApi: {
      buildFromTemplate: (template) => {
        menuTemplate = template;
        return { template };
      },
    },
  });

  assert.equal(resolvedIconPath, '/tmp/assistant-tray.png');
  assert.equal(tray.toolTip, 'StockPulse');
  assert.deepEqual(
    menuTemplate.filter((item) => item.label).map((item) => item.label),
    [
      'Open Floating Assistant',
      'Local Models…',
      'Show Main Window',
      'Hide Main Window',
      'Quit StockPulse',
    ]
  );
  let navigatedUrl = '';
  let resolveNavigation;
  const navigationCompleted = new Promise((resolve) => {
    resolveNavigation = resolve;
  });
  mainModule.__setMainWindowForTest({
    isDestroyed: () => false,
    isMinimized: () => false,
    isVisible: () => true,
    show: () => undefined,
    focus: () => undefined,
    loadURL: async (url) => {
      navigatedUrl = url;
      resolveNavigation();
    },
  });
  mainModule.__setDesktopDeepLinkStateForTest({
    mainPageUrl: 'http://127.0.0.1:8123/?desktop_version=3.21.0&cache_bust=123',
    ready: true,
  });
  menuTemplate.find((item) => item.label === 'Local Models…').click();
  await navigationCompleted;
  const localModelsUrl = new URL(navigatedUrl);
  assert.equal(localModelsUrl.pathname, '/settings');
  assert.equal(localModelsUrl.searchParams.get('section'), 'ai_models');
  assert.equal(localModelsUrl.searchParams.get('view'), 'local_models');
  assert.equal(mainModule.resolveDesktopAssistantTrayIconPath({
    packaged: true,
    resourcesPath: '/Applications/StockPulse.app/Contents/Resources',
  }), '/Applications/StockPulse.app/Contents/Resources/assistant-tray.png');
});

test('main-window close hides to tray unless the application is quitting', (t) => {
  const mainModule = loadMainModule(t);
  let hidden = 0;
  let prevented = 0;
  mainModule.__setMainWindowForTest({
    isDestroyed: () => false,
    hide: () => {
      hidden += 1;
    },
  });
  mainModule.__setDesktopTrayForTest({
    isDestroyed: () => false,
  });

  assert.equal(mainModule.handleMainWindowClose({
    preventDefault: () => {
      prevented += 1;
    },
  }), true);
  assert.equal(hidden, 1);
  assert.equal(prevented, 1);

  mainModule.__setDesktopIsQuittingForTest(true);
  assert.equal(mainModule.handleMainWindowClose({
    preventDefault: () => {
      prevented += 1;
    },
  }), false);
  assert.equal(hidden, 1);
  assert.equal(prevented, 1);
});

test('main-window close keeps the original lifecycle when tray creation failed', (t) => {
  const mainModule = loadMainModule(t);
  let hidden = 0;
  let prevented = 0;
  mainModule.__setMainWindowForTest({
    isDestroyed: () => false,
    hide: () => {
      hidden += 1;
    },
  });
  mainModule.__setDesktopTrayForTest(null);

  assert.equal(mainModule.handleMainWindowClose({
    preventDefault: () => {
      prevented += 1;
    },
  }), false);
  assert.equal(hidden, 0);
  assert.equal(prevented, 0);
});

test('desktop deep-link parser preserves allowlisted Web paths and search state', (t) => {
  const mainModule = loadMainModule(t);
  const acceptedLinks = new Map([
    ['stockpulse://app/?stock=AAPL&workspace=watchlist', '/?stock=AAPL&workspace=watchlist'],
    ['stockpulse://app/chat?session=run-123', '/chat?session=run-123'],
    ['stockpulse://app/portfolio?account=7', '/portfolio?account=7'],
    ['stockpulse://app/decision-signals?stock=HK00700&view=timeline', '/decision-signals?stock=HK00700&view=timeline'],
    ['stockpulse://app/stocks/600519?period=weekly&days=30', '/stocks/600519?period=weekly&days=30'],
    ['stockpulse://app/alerts', '/alerts'],
    ['stockpulse://app/backtest', '/backtest'],
    ['stockpulse://app/screening', '/screening'],
    ['stockpulse://app/settings', '/settings'],
    ['STOCKPULSE://APP/usage?keep=yes', '/usage?keep=yes'],
  ]);

  for (const [input, expected] of acceptedLinks) {
    assert.equal(mainModule.parseDesktopDeepLink(input), expected, input);
  }
  assert.equal(
    mainModule.extractDesktopDeepLink(['StockPulse', '--flag', 'stockpulse://app/settings']),
    'stockpulse://app/settings'
  );
  assert.equal(mainModule.extractDesktopDeepLink(['StockPulse', '--flag']), null);
});

test('desktop deep-link parser rejects external, ambiguous, and smuggled routes', (t) => {
  const mainModule = loadMainModule(t);
  const rejectedLinks = [
    'https://example.com/settings',
    'stockpulse://evil.example/settings',
    'stockpulse://app@evil.example/settings',
    'stockpulse://app:443/settings',
    'stockpulse:///settings',
    'stockpulse://settings',
    'stockpulse://app/settings#https://evil.example',
    'stockpulse://app/login',
    'stockpulse://app/playground',
    'stockpulse://app//evil.example',
    'stockpulse://app/foo/../settings',
    'stockpulse://app/%2e%2e/settings',
    'stockpulse://app/stocks/%2FAAPL',
    ' stockpulse://app/settings',
    `stockpulse://app/settings?value=${'x'.repeat(4096)}`,
  ];

  for (const input of rejectedLinks) {
    assert.equal(mainModule.parseDesktopDeepLink(input), null, input);
  }
});

test('desktop deep links stay on the selected private Web origin', (t) => {
  const mainModule = loadMainModule(t);
  const targetUrl = new URL(mainModule.buildDesktopDeepLinkTargetUrl(
    'http://127.0.0.1:8123/?desktop_version=3.21.0&cache_bust=123',
    '/portfolio?account=7&desktop_version=spoofed&keep=yes'
  ));

  assert.equal(targetUrl.origin, 'http://127.0.0.1:8123');
  assert.equal(targetUrl.pathname, '/portfolio');
  assert.equal(targetUrl.searchParams.get('account'), '7');
  assert.equal(targetUrl.searchParams.get('keep'), 'yes');
  assert.equal(targetUrl.searchParams.get('desktop_version'), '3.21.0');
  assert.equal(targetUrl.searchParams.get('cache_bust'), '123');
  assert.throws(
    () => mainModule.buildDesktopDeepLinkTargetUrl(
      'http://127.0.0.1:8123/?desktop_version=3.21.0',
      'https://evil.example/settings'
    ),
    /private Web origin/
  );
});

test('desktop lifecycle registers the protocol and OS URL handlers', (t) => {
  const protocolCalls = [];
  const eventHandlers = new Map();
  const mainModule = loadMainModule(t, {
    app: {
      on: (eventName, handler) => {
        eventHandlers.set(eventName, handler);
      },
      setAsDefaultProtocolClient: (...args) => {
        protocolCalls.push(args);
        return true;
      },
    },
  });

  assert.deepEqual(protocolCalls, [['stockpulse']]);
  assert.equal(eventHandlers.get('open-url'), mainModule.handleDesktopOpenUrl);
  assert.equal(eventHandlers.get('second-instance'), mainModule.handleDesktopSecondInstance);

  protocolCalls.length = 0;
  assert.equal(mainModule.registerDesktopProtocolClient({
    defaultApp: true,
    executablePath: '/Applications/Electron.app/Contents/MacOS/Electron',
    argv: ['electron', '/repo/apps/dsa-desktop/main.js'],
  }), true);
  assert.deepEqual(protocolCalls, [[
    'stockpulse',
    '/Applications/Electron.app/Contents/MacOS/Electron',
    ['/repo/apps/dsa-desktop/main.js'],
  ]]);
});

test('second-instance deep links restore and focus before routing', async (t) => {
  const mainModule = loadMainModule(t);
  const lifecycle = [];
  const fakeWindow = {
    isDestroyed: () => false,
    isMinimized: () => true,
    restore: () => lifecycle.push('restore'),
    show: () => lifecycle.push('show'),
    focus: () => lifecycle.push('focus'),
    loadURL: async (url) => {
      lifecycle.push(`load:${url}`);
    },
  };
  mainModule.__setMainWindowForTest(fakeWindow);
  mainModule.__setDesktopDeepLinkStateForTest({
    mainPageUrl: 'http://127.0.0.1:8123/?desktop_version=3.21.0&cache_bust=123',
    ready: true,
  });

  assert.equal(await mainModule.handleDesktopSecondInstance(
    null,
    ['StockPulse', 'stockpulse://app/portfolio?account=7']
  ), true);
  assert.deepEqual(lifecycle.slice(0, 3), ['restore', 'show', 'focus']);
  const loadedUrl = new URL(lifecycle[3].slice('load:'.length));
  assert.equal(loadedUrl.pathname, '/portfolio');
  assert.equal(loadedUrl.searchParams.get('account'), '7');
  assert.equal(loadedUrl.searchParams.get('desktop_version'), '3.21.0');

  const loadCount = lifecycle.filter((entry) => entry.startsWith('load:')).length;
  assert.equal(await mainModule.handleDesktopSecondInstance(
    null,
    ['StockPulse', 'stockpulse://evil.example/settings']
  ), false);
  assert.equal(lifecycle.filter((entry) => entry.startsWith('load:')).length, loadCount);
});

test('macOS open-url deep links wait for the private Web origin to become ready', async (t) => {
  const mainModule = loadMainModule(t);
  const loadedUrls = [];
  let prevented = false;
  mainModule.__setMainWindowForTest({
    isDestroyed: () => false,
    isMinimized: () => false,
    show: () => undefined,
    focus: () => undefined,
    loadURL: async (url) => loadedUrls.push(url),
  });
  mainModule.__setDesktopDeepLinkStateForTest();

  assert.equal(await mainModule.handleDesktopOpenUrl({
    preventDefault: () => {
      prevented = true;
    },
  }, 'stockpulse://app/stocks/AAPL?period=weekly'), false);
  assert.equal(prevented, true);
  assert.equal(loadedUrls.length, 0);
  const pendingRoute = mainModule.__getPendingDesktopDeepLinkRouteForTest();
  assert.equal(pendingRoute, '/stocks/AAPL?period=weekly');

  mainModule.__setDesktopDeepLinkStateForTest({
    mainPageUrl: 'http://127.0.0.1:8123/?desktop_version=3.21.0&cache_bust=123',
    ready: true,
    pendingRoute,
  });
  assert.equal(await mainModule.flushPendingDesktopDeepLink(), true);
  assert.equal(new URL(loadedUrls[0]).pathname, '/stocks/AAPL');
});

test('buildMainPageUrl includes desktop version and cache buster', (t) => {
  const mainModule = loadMainModule(t, {
    app: {
      getVersion: () => ' 3.17.1 ',
    },
  });

  assert.equal(
    mainModule.buildMainPageUrl(8123, 1234567890),
    'http://127.0.0.1:8123/?desktop_version=3.17.1&cache_bust=1234567890'
  );
});

test('buildMainPageUrl uses a connect host when provided', (t) => {
  const mainModule = loadMainModule(t, {
    app: {
      getVersion: () => '3.17.1',
    },
  });

  assert.equal(
    mainModule.buildMainPageUrl(8123, 1234567890, '192.168.1.9'),
    'http://192.168.1.9:8123/?desktop_version=3.17.1&cache_bust=1234567890'
  );
});

test('resolveDesktopConnectHost keeps desktop navigation local for public binds', (t) => {
  const mainModule = loadMainModule(t);

  assert.equal(mainModule.resolveDesktopConnectHost('0.0.0.0'), '127.0.0.1');
  assert.equal(mainModule.resolveDesktopConnectHost('::'), '127.0.0.1');
  assert.equal(mainModule.resolveDesktopConnectHost('*'), '127.0.0.1');
  assert.equal(mainModule.resolveDesktopConnectHost('[::]'), '127.0.0.1');
  assert.equal(mainModule.resolveDesktopConnectHost('192.168.1.9'), '192.168.1.9');
});

test('buildBackendEnvironment extends macOS GUI PATH with Homebrew CLI directories', (t) => {
  const mainModule = loadMainModule(t, { platform: 'darwin' });

  const env = mainModule.buildBackendEnvironment({
    envFile: '/tmp/dsa/.env',
    dbPath: '/tmp/dsa/data.db',
    logDir: '/tmp/dsa/logs',
    sourceEnv: {
      PATH: '/usr/bin:/bin:/usr/sbin:/sbin',
      CUSTOM_FLAG: 'kept',
    },
  });

  const entries = env.PATH.split(POSIX_PATH_DELIMITER);
  assert.deepEqual(entries.slice(0, 4), ['/usr/bin', '/bin', '/usr/sbin', '/sbin']);
  assert.ok(entries.includes('/opt/homebrew/bin'));
  assert.ok(entries.includes('/usr/local/bin'));
  assert.ok(entries.includes('/opt/homebrew/sbin'));
  assert.ok(entries.includes('/usr/local/sbin'));
  assert.equal(env.CUSTOM_FLAG, 'kept');
  assert.equal(env.DSA_DESKTOP_MODE, 'true');
  assert.equal(env.ENV_FILE, '/tmp/dsa/.env');
  assert.equal(env.DATABASE_PATH, '/tmp/dsa/data.db');
  assert.equal(env.LOG_DIR, '/tmp/dsa/logs');
  assert.equal(env.WEBUI_HOST, '127.0.0.1');
});

test('buildBackendEnvironment keeps non-macOS PATH unchanged', (t) => {
  const mainModule = loadMainModule(t, { platform: 'linux' });

  const env = mainModule.buildBackendEnvironment({
    envFile: '/tmp/dsa/.env',
    dbPath: '/tmp/dsa/data.db',
    logDir: '/tmp/dsa/logs',
    sourceEnv: {
      PATH: '/custom/bin:/usr/bin',
    },
  });

  assert.equal(env.PATH, '/custom/bin:/usr/bin');
});

test('buildBackendEnvironment keeps the daily provider cache in Desktop runtime data by default', (t) => {
  const mainModule = loadMainModule(t, { platform: 'darwin' });
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-provider-cache-'));
  t.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }));
  const envFile = path.join(tempRoot, '.env');
  const dbPath = path.join(tempRoot, 'data', 'stock_analysis.db');

  const env = mainModule.buildBackendEnvironment({
    envFile,
    dbPath,
    logDir: path.join(tempRoot, 'logs'),
    sourceEnv: {},
  });

  assert.equal(
    env.PROVIDER_DAILY_CACHE_DIR,
    path.join(tempRoot, 'data', 'provider_cache', 'daily')
  );
});

test('buildBackendEnvironment preserves explicit daily provider cache paths', (t) => {
  const mainModule = loadMainModule(t, { platform: 'darwin' });
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-provider-cache-'));
  t.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }));
  const envFile = path.join(tempRoot, '.env');
  const dbPath = path.join(tempRoot, 'data', 'stock_analysis.db');
  fs.writeFileSync(
    envFile,
    'CACHE_ROOT=/tmp/file-cache\nPROVIDER_DAILY_CACHE_DIR=${CACHE_ROOT}/daily\n',
    'utf-8'
  );

  const envFileOverride = mainModule.buildBackendEnvironment({
    envFile,
    dbPath,
    logDir: path.join(tempRoot, 'logs'),
    sourceEnv: {},
  });
  const processOverride = mainModule.buildBackendEnvironment({
    envFile,
    dbPath,
    logDir: path.join(tempRoot, 'logs'),
    sourceEnv: {
      PROVIDER_DAILY_CACHE_DIR: '/tmp/process-cache/daily',
    },
  });

  assert.equal(envFileOverride.PROVIDER_DAILY_CACHE_DIR, '/tmp/file-cache/daily');
  assert.equal(processOverride.PROVIDER_DAILY_CACHE_DIR, '/tmp/process-cache/daily');
});

test('buildBackendEnvironment pins WEBUI_PORT to the Electron-selected backend port', (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });

  const env = mainModule.buildBackendEnvironment({
    envFile: 'C:\\Users\\user\\AppData\\Roaming\\Daily Stock Analysis\\.env',
    dbPath: 'C:\\Users\\user\\AppData\\Roaming\\Daily Stock Analysis\\data\\stock_analysis.db',
    logDir: 'C:\\Users\\user\\AppData\\Roaming\\Daily Stock Analysis\\logs',
    port: 8000,
    sourceEnv: {
      PATH: 'C:\\Windows\\System32',
      WEBUI_PORT: '18000',
    },
  });

  assert.equal(env.WEBUI_PORT, '8000');
  assert.equal(env.WEBUI_HOST, '127.0.0.1');
});

test('resolveBackendBindHost reads WEBUI_HOST from env file', (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-host-'));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  const envPath = path.join(tmpDir, '.env');
  fs.writeFileSync(envPath, 'WEBUI_HOST=0.0.0.0 # allow LAN\nWEBUI_PORT=8000\n', 'utf-8');

  assert.equal(mainModule.readEnvFileValue(envPath, 'WEBUI_HOST'), '0.0.0.0');
  assert.equal(
    mainModule.resolveBackendBindHost({ envFile: envPath, sourceEnv: {} }),
    '0.0.0.0'
  );
});

test('resolveBackendBindHost expands WEBUI_HOST dotenv references', (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-host-'));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  const envPath = path.join(tmpDir, '.env');
  fs.writeFileSync(envPath, 'BIND_HOST=0.0.0.0\nWEBUI_HOST=${BIND_HOST}\n', 'utf-8');

  assert.equal(mainModule.readEnvFileValue(envPath, 'WEBUI_HOST', {}), '0.0.0.0');
  assert.equal(
    mainModule.resolveBackendBindHost({ envFile: envPath, sourceEnv: {} }),
    '0.0.0.0'
  );
});

test('resolveBackendBindHost handles quoted WEBUI_HOST with inline comment', (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-host-'));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  const envPath = path.join(tmpDir, '.env');
  fs.writeFileSync(envPath, 'WEBUI_HOST="0.0.0.0" # allow LAN\n', 'utf-8');

  assert.equal(mainModule.readEnvFileValue(envPath, 'WEBUI_HOST', {}), '0.0.0.0');
  assert.equal(
    mainModule.resolveBackendBindHost({ envFile: envPath, sourceEnv: {} }),
    '0.0.0.0'
  );
});

test('resolveBackendBindHost supports dotenv default expansion', (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-host-'));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  const envPath = path.join(tmpDir, '.env');
  fs.writeFileSync(envPath, 'WEBUI_HOST=${MISSING_HOST:-127.0.0.1}\n', 'utf-8');

  assert.equal(mainModule.readEnvFileValue(envPath, 'WEBUI_HOST', {}), '127.0.0.1');
  assert.equal(
    mainModule.resolveBackendBindHost({ envFile: envPath, sourceEnv: {} }),
    '127.0.0.1'
  );
});

test('resolveBackendBindHost keeps process WEBUI_HOST override ahead of env file', (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-host-'));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  const envPath = path.join(tmpDir, '.env');
  fs.writeFileSync(envPath, 'WEBUI_HOST=0.0.0.0\n', 'utf-8');

  assert.equal(
    mainModule.resolveBackendBindHost({
      envFile: envPath,
      sourceEnv: { WEBUI_HOST: '192.168.1.9' },
    }),
    '192.168.1.9'
  );
});

test('resolveBackendBindHost normalizes wildcard WEBUI_HOST values', (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-host-'));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  const envPath = path.join(tmpDir, '.env');
  fs.writeFileSync(envPath, 'WEBUI_HOST=*\n', 'utf-8');

  assert.equal(
    mainModule.resolveBackendBindHost({ envFile: envPath, sourceEnv: {} }),
    '0.0.0.0'
  );
  assert.equal(
    mainModule.resolveBackendBindHost({
      envFile: envPath,
      sourceEnv: { WEBUI_HOST: '[::]' },
    }),
    '::'
  );
});

test('buildBackendEnvironment injects env file WEBUI_HOST into backend process', (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-host-'));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  const envPath = path.join(tmpDir, '.env');
  fs.writeFileSync(envPath, 'BIND_HOST=0.0.0.0\nWEBUI_HOST=${BIND_HOST}\n', 'utf-8');

  const env = mainModule.buildBackendEnvironment({
    envFile: envPath,
    dbPath: 'C:\\Users\\user\\AppData\\Roaming\\Daily Stock Analysis\\data\\stock_analysis.db',
    logDir: 'C:\\Users\\user\\AppData\\Roaming\\Daily Stock Analysis\\logs',
    port: 8000,
    sourceEnv: {
      PATH: 'C:\\Windows\\System32',
    },
  });

  assert.equal(env.WEBUI_HOST, '0.0.0.0');
  assert.equal(env.WEBUI_PORT, '8000');
});

test('buildBackendEnvironment normalizes wildcard host for backend env', (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });

  const wildcardEnv = mainModule.buildBackendEnvironment({
    envFile: '/tmp/dsa/.env',
    dbPath: '/tmp/dsa/data.db',
    logDir: '/tmp/dsa/logs',
    port: 8000,
    host: '*',
    sourceEnv: {},
  });
  const ipv6Env = mainModule.buildBackendEnvironment({
    envFile: '/tmp/dsa/.env',
    dbPath: '/tmp/dsa/data.db',
    logDir: '/tmp/dsa/logs',
    port: 8001,
    host: '[::]',
    sourceEnv: {},
  });

  assert.equal(wildcardEnv.WEBUI_HOST, '0.0.0.0');
  assert.equal(ipv6Env.WEBUI_HOST, '::');
});

test('buildBackendArgs passes resolved host to main.py', (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });

  assert.deepEqual(mainModule.buildBackendArgs({ host: '0.0.0.0', port: 8123 }), [
    '--serve-only',
    '--host',
    '0.0.0.0',
    '--port',
    '8123',
  ]);
});

test('buildBackendArgs normalizes wildcard hosts before spawning main.py', (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });

  assert.deepEqual(mainModule.buildBackendArgs({ host: '*', port: 8123 }), [
    '--serve-only',
    '--host',
    '0.0.0.0',
    '--port',
    '8123',
  ]);
  assert.deepEqual(mainModule.buildBackendArgs({ host: '[::]', port: 8124 }), [
    '--serve-only',
    '--host',
    '::',
    '--port',
    '8124',
  ]);
});

test('findAvailablePort listens on requested bind host', async (t) => {
  let listenedHost = '';
  const fakeNet = {
    createServer: () => {
      const server = new EventEmitter();
      server.listen = (_port, host) => {
        listenedHost = host;
        process.nextTick(() => server.emit('listening'));
      };
      server.close = (callback) => {
        if (callback) {
          callback();
        }
      };
      return server;
    },
  };
  const mainModule = loadMainModule(t, { platform: 'win32', net: fakeNet });

  const port = await mainModule.findAvailablePort(8123, 8123, '0.0.0.0');

  assert.equal(port, 8123);
  assert.equal(listenedHost, '0.0.0.0');
});

test('findAvailablePort normalizes wildcard bind hosts before listening', async (t) => {
  const listenedHosts = [];
  const fakeNet = {
    createServer: () => {
      const server = new EventEmitter();
      server.listen = (_port, host) => {
        listenedHosts.push(host);
        process.nextTick(() => server.emit('listening'));
      };
      server.close = (callback) => {
        if (callback) {
          callback();
        }
      };
      return server;
    },
  };
  const mainModule = loadMainModule(t, { platform: 'win32', net: fakeNet });

  await mainModule.findAvailablePort(8123, 8123, '*');
  await mainModule.findAvailablePort(8124, 8124, '[::]');

  assert.deepEqual(listenedHosts, ['0.0.0.0', '::']);
});

test('startBackend passes WEBUI_HOST from env file to backend args and env', (t) => {
  const previousWebuiHost = process.env.WEBUI_HOST;
  const previousProviderDailyCacheDir = process.env.PROVIDER_DAILY_CACHE_DIR;
  delete process.env.WEBUI_HOST;
  delete process.env.PROVIDER_DAILY_CACHE_DIR;
  t.after(() => {
    if (previousWebuiHost === undefined) {
      delete process.env.WEBUI_HOST;
    } else {
      process.env.WEBUI_HOST = previousWebuiHost;
    }
    if (previousProviderDailyCacheDir === undefined) {
      delete process.env.PROVIDER_DAILY_CACHE_DIR;
    } else {
      process.env.PROVIDER_DAILY_CACHE_DIR = previousProviderDailyCacheDir;
    }
  });
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-host-'));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  const envPath = path.join(tmpDir, '.env');
  fs.writeFileSync(envPath, 'BIND_HOST=0.0.0.0\nWEBUI_HOST=${BIND_HOST}\n', 'utf-8');
  const spawned = [];
  const fakeBackendProcess = new EventEmitter();
  fakeBackendProcess.stdout = new EventEmitter();
  fakeBackendProcess.stderr = new EventEmitter();
  fakeBackendProcess.exitCode = null;
  fakeBackendProcess.signalCode = null;
  fakeBackendProcess.kill = () => true;
  const mainModule = loadMainModule(t, {
    platform: 'win32',
    childProcess: {
      spawn: (command, args, options) => {
        spawned.push({ command, args, options });
        return fakeBackendProcess;
      },
    },
  });
  t.after(() => mainModule.__setBackendProcessForTest(null));

  mainModule.startBackend({
    port: 8123,
    envFile: envPath,
    dbPath: path.join(tmpDir, 'stock_analysis.db'),
    logDir: path.join(tmpDir, 'logs'),
  });

  assert.equal(spawned.length, 1);
  assert.deepEqual(spawned[0].args.slice(-5), [
    '--serve-only',
    '--host',
    '0.0.0.0',
    '--port',
    '8123',
  ]);
  assert.equal(spawned[0].options.env.WEBUI_HOST, '0.0.0.0');
  assert.equal(
    spawned[0].options.env.PROVIDER_DAILY_CACHE_DIR,
    path.join(tmpDir, 'provider_cache', 'daily')
  );
});

test('startBackend ignores lifecycle events from a replaced process generation', async (t) => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-backend-generation-'));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  const backendProcesses = Array.from({ length: 2 }, (_value, index) => {
    const processRef = new EventEmitter();
    processRef.pid = 4100 + index;
    processRef.exitCode = null;
    processRef.signalCode = null;
    processRef.killed = false;
    processRef.stdout = new EventEmitter();
    processRef.stderr = new EventEmitter();
    processRef.kill = () => {
      processRef.killed = true;
      return true;
    };
    return processRef;
  });
  let spawnIndex = 0;
  const mainModule = loadMainModule(t, {
    platform: 'darwin',
    childProcess: {
      spawn: () => backendProcesses[spawnIndex++],
    },
  });
  t.after(() => mainModule.__setBackendProcessForTest(null));
  const launchOptions = {
    port: 8123,
    envFile: path.join(tmpDir, '.env'),
    dbPath: path.join(tmpDir, 'stock_analysis.db'),
    logDir: path.join(tmpDir, 'logs'),
  };

  mainModule.startBackend(launchOptions);
  const stoppedOldGeneration = mainModule.stopBackend();
  mainModule.startBackend({ ...launchOptions, port: 8124 });
  mainModule.__setDesktopAssistantStateForTest({ webReady: true });

  backendProcesses[0].emit('error', new Error('stale backend failed'));
  assert.equal(mainModule.buildDesktopAssistantState().serviceStatus, 'ready');
  backendProcesses[0].exitCode = 0;
  backendProcesses[0].emit('exit', 0, null);
  await stoppedOldGeneration;
  assert.equal(mainModule.buildDesktopAssistantState().serviceStatus, 'ready');
  assert.equal(mainModule.__getBackendProcessForTest(), backendProcesses[1]);

  backendProcesses[1].emit('error', new Error('current backend failed'));
  assert.equal(mainModule.buildDesktopAssistantState().serviceStatus, 'unavailable');
});

test('extendMacDesktopBackendPath preserves existing order and avoids duplicates', (t) => {
  const mainModule = loadMainModule(t, { platform: 'darwin' });

  const extended = mainModule.extendMacDesktopBackendPath(
    '/opt/homebrew/bin:/custom/bin:/usr/bin:/custom/bin'
  );
  const entries = extended.split(POSIX_PATH_DELIMITER);

  assert.deepEqual(entries.slice(0, 3), ['/opt/homebrew/bin', '/custom/bin', '/usr/bin']);
  assert.equal(entries.filter((entry) => entry === '/opt/homebrew/bin').length, 1);
  assert.equal(entries.filter((entry) => entry === '/custom/bin').length, 1);
  assert.ok(entries.includes('/usr/local/bin'));
  assert.ok(entries.includes('/bin'));
  assert.ok(entries.includes('/usr/sbin'));
  assert.ok(entries.includes('/sbin'));
});

test('extractReleaseMetadata ignores releases without semver tags', (t) => {
  const mainModule = loadMainModule(t);

  assert.equal(
    mainModule.extractReleaseMetadata({
      tag_name: 'desktop-latest',
      html_url: 'https://github.com/SiinXu/stock-pulse-ai/releases/tag/desktop-latest',
    }),
    null
  );
});

test('evaluateReleaseUpdate reports update-available when release is newer', (t) => {
  const mainModule = loadMainModule(t);
  const state = mainModule.evaluateReleaseUpdate({
    currentVersion: '3.12.0',
    release: {
      tag_name: 'v3.13.0',
      html_url: 'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0',
      published_at: '2026-04-25T01:00:00Z',
      name: 'v3.13.0',
    },
    checkedAt: '2026-04-25T01:02:00Z',
  });

  assert.equal(state.status, mainModule.UPDATE_STATUS.UPDATE_AVAILABLE);
  assert.equal(state.currentVersion, '3.12.0');
  assert.equal(state.latestVersion, '3.13.0');
  assert.equal(state.releaseUrl, 'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0');
  assert.equal(state.checkedAt, '2026-04-25T01:02:00Z');
  assert.equal(state.publishedAt, '2026-04-25T01:00:00Z');
  assert.match(state.message, /发现新版本 3\.13\.0/);
});

test('evaluateReleaseUpdate reports up-to-date when version is current', (t) => {
  const mainModule = loadMainModule(t);
  const state = mainModule.evaluateReleaseUpdate({
    currentVersion: '3.13.0',
    release: {
      tag_name: 'v3.13.0',
      html_url: 'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0',
    },
    checkedAt: '2026-04-25T01:02:00Z',
  });

  assert.equal(state.status, mainModule.UPDATE_STATUS.UP_TO_DATE);
  assert.equal(state.latestVersion, '3.13.0');
  assert.equal(state.releaseUrl, 'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0');
  assert.equal(state.checkedAt, '2026-04-25T01:02:00Z');
  assert.equal(state.publishedAt, '');
});

test('evaluateReleaseUpdate reports error when current version is invalid', (t) => {
  const mainModule = loadMainModule(t);
  const state = mainModule.evaluateReleaseUpdate({
    currentVersion: 'build-20260425',
    release: {
      tag_name: 'v3.13.0',
      html_url: 'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0',
    },
    checkedAt: '2026-04-25T01:02:00Z',
  });

  assert.equal(state.status, mainModule.UPDATE_STATUS.ERROR);
  assert.match(state.message, /不是有效的语义化版本/);
});

test('checkForDesktopUpdates delegates to release fetcher', async (t) => {
  const mainModule = loadMainModule(t);
  const state = await mainModule.checkForDesktopUpdates({
    currentVersion: '3.12.0',
    fetchLatestRelease: async () => ({
      tag_name: 'v3.13.0',
      html_url: '',
    }),
  });

  assert.equal(state.status, mainModule.UPDATE_STATUS.UPDATE_AVAILABLE);
  assert.equal(state.releaseUrl, mainModule.RELEASES_PAGE_URL);
});

test('sanitizeReleaseUrl falls back for non-release links', (t) => {
  const mainModule = loadMainModule(t);

  assert.equal(
    mainModule.sanitizeReleaseUrl('https://example.com/not-allowed'),
    mainModule.RELEASES_PAGE_URL
  );
  assert.equal(
    mainModule.sanitizeReleaseUrl(
      `https://github.com/${mainModule.GITHUB_OWNER}/${mainModule.GITHUB_REPO}/releases/tag/v3.13.0`
    ),
    `https://github.com/${mainModule.GITHUB_OWNER}/${mainModule.GITHUB_REPO}/releases/tag/v3.13.0`
  );
});

test('fetchLatestReleaseJson rejects when response stream errors', async (t) => {
  const mainModule = loadMainModule(t);
  const response = new EventEmitter();
  response.statusCode = 200;
  response.complete = false;
  let destroyed = false;

  const request = () => {
    const req = new EventEmitter();
    req.destroyed = false;
    req.setTimeout = () => undefined;
    req.destroy = () => {
      destroyed = true;
      req.destroyed = true;
    };
    req.end = () => {
      process.nextTick(() => {
        request.onResponse(response);
        response.emit('error', new Error('stream failed'));
      });
    };
    return req;
  };
  request.onResponse = () => undefined;

  const pending = mainModule.fetchLatestReleaseJson({
    request: (_url, _options, onResponse) => {
      request.onResponse = onResponse;
      return request();
    },
  });

  await assert.rejects(pending, /stream failed/);
  assert.equal(destroyed, true);
});

test('auto download prompt falls back to error when install path fails', async (t) => {
  const updaterEvents = {};
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa desktop updater '));
  const exeDir = path.join(tempRoot, 'app');
  const userDataDir = path.join(tempRoot, 'userData');
  const exePath = path.join(exeDir, 'Daily Stock Analysis.exe');
  const uninstallPath = path.join(exeDir, 'Uninstall Daily Stock Analysis.exe');
  const envFile = path.join(exeDir, '.env');
  const backupRoot = path.join(userDataDir, '.dsa-desktop-update-backup');
  const originalRemove = fs.rmSync;
  let quitAndInstallArgs = null;
  const fakeUpdater = {
    autoDownload: true,
    autoInstallOnAppQuit: false,
    on: (event, handler) => {
      updaterEvents[event] = handler;
    },
    checkForUpdates: async () => {
      if (typeof updaterEvents['update-downloaded'] === 'function') {
        await updaterEvents['update-downloaded']({
          version: 'v3.13.0',
          releaseDate: '2026-04-25T01:00:00Z',
          releaseName: 'v3.13.0',
        });
      }
    },
    quitAndInstall: (...args) => {
      quitAndInstallArgs = args;
      throw new Error('安装进程启动失败');
    },
  };

  const mainModule = loadMainModule(t, {
    dialog: {
      showMessageBox: async () => ({ response: 1 }),
    },
    electronUpdater: fakeUpdater,
    platform: 'win32',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return exePath;
        }
        return userDataDir;
      },
    },
  });

  fs.mkdirSync(exeDir, { recursive: true });
  fs.mkdirSync(userDataDir, { recursive: true });
  fs.writeFileSync(envFile, 'RUN_MODE=desktop\n');
  fs.writeFileSync(uninstallPath, '');

  mainModule.__setMainWindowForTest({
    isDestroyed: () => false,
    webContents: {
      send: () => undefined,
    },
  });

  await mainModule.__getIpcMainHandler('desktop:check-for-updates')();
  let state = await mainModule.__getIpcMainHandler('desktop:get-update-state')();
  for (let idx = 0; idx < 12 && state.status !== mainModule.UPDATE_STATUS.ERROR; idx += 1) {
    await new Promise((resolve) => {
      setTimeout(resolve, 30);
    });
    state = await mainModule.__getIpcMainHandler('desktop:get-update-state')();
  }

  assert.equal(state.status, mainModule.UPDATE_STATUS.ERROR);
  assert.match(state.message, /更新安装失败/);
  assert.equal(state.updateMode, mainModule.UPDATE_MODE.AUTO);
  assert.deepEqual(quitAndInstallArgs, [true, true]);
  assert.equal(fakeUpdater.installDirectory, exeDir);
  assert.equal(fs.existsSync(backupRoot), false);
  assert.equal(fs.existsSync(path.join(backupRoot, 'runtime-state.json')), false);

  t.after(() => {
    originalRemove(tempRoot, { recursive: true, force: true });
  });
});

test('auto update backup copies AlphaSift hotspot detail directories recursively', async (t) => {
  const updaterEvents = {};
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa desktop updater details '));
  const exeDir = path.join(tempRoot, 'app');
  const userDataDir = path.join(tempRoot, 'userData');
  const exePath = path.join(exeDir, 'Daily Stock Analysis.exe');
  const uninstallPath = path.join(exeDir, 'Uninstall Daily Stock Analysis.exe');
  const detailRelativePath = path.join('data', 'alphasift', 'hotspot_details');
  const detailFileRelativePath = path.join(detailRelativePath, 'ai-compute.json');
  const detailFile = path.join(exeDir, detailFileRelativePath);
  const backupRoot = path.join(userDataDir, '.dsa-desktop-update-backup');
  let quitAndInstallArgs = null;
  const fakeUpdater = {
    autoDownload: true,
    autoInstallOnAppQuit: false,
    on: (event, handler) => {
      updaterEvents[event] = handler;
    },
    checkForUpdates: async () => {
      if (typeof updaterEvents['update-downloaded'] === 'function') {
        updaterEvents['update-downloaded']({
          version: 'v3.13.0',
          releaseDate: '2026-04-25T01:00:00Z',
          releaseName: 'v3.13.0',
        });
      }
    },
    quitAndInstall: (...args) => {
      quitAndInstallArgs = args;
    },
  };

  const mainModule = loadMainModule(t, {
    dialog: {
      showMessageBox: async () => ({ response: 1 }),
    },
    electronUpdater: fakeUpdater,
    platform: 'win32',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return exePath;
        }
        return userDataDir;
      },
    },
  });

  fs.mkdirSync(path.dirname(detailFile), { recursive: true });
  fs.mkdirSync(userDataDir, { recursive: true });
  fs.writeFileSync(uninstallPath, '');
  fs.writeFileSync(detailFile, '{"topic":"AI算力"}\n', 'utf-8');

  mainModule.__setMainWindowForTest({
    isDestroyed: () => false,
    webContents: {
      send: () => undefined,
    },
  });

  await mainModule.__getIpcMainHandler('desktop:check-for-updates')();
  for (let idx = 0; idx < 12 && !quitAndInstallArgs; idx += 1) {
    await new Promise((resolve) => {
      setTimeout(resolve, 30);
    });
  }

  assert.deepEqual(quitAndInstallArgs, [true, true]);
  assert.equal(fs.readFileSync(path.join(backupRoot, detailFileRelativePath), 'utf-8'), '{"topic":"AI算力"}\n');
  assert.ok(JSON.parse(fs.readFileSync(path.join(backupRoot, 'runtime-state.json'), 'utf-8')).files.includes(detailRelativePath));

  t.after(() => {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });
});

test('desktop update backup list includes WAL and SHM artifacts', (t) => {
  const mainModule = loadMainModule(t);
  const files = mainModule.DESKTOP_UPDATE_RUNTIME_RELATIVE_FILES || [];
  assert.equal(Array.isArray(files), true);
  assert.ok(files.includes(path.join('data', 'stock_analysis.db')));
  assert.ok(files.includes(path.join('data', 'stock_analysis.db-wal')));
  assert.ok(files.includes(path.join('data', 'stock_analysis.db-shm')));
  assert.ok(files.includes(path.join('logs', 'desktop.log')));
});

test('desktop update backup list preserves AlphaSift caches', (t) => {
  const mainModule = loadMainModule(t);
  const files = mainModule.DESKTOP_UPDATE_RUNTIME_RELATIVE_FILES || [];
  assert.ok(files.includes(path.join('data', 'alphasift', 'hotspots.json')));
  assert.ok(files.includes(path.join('data', 'alphasift', 'hotspot.history.jsonl')));
  assert.ok(files.includes(path.join('data', 'alphasift', 'hotspot_details')));
  assert.ok(files.includes(path.join('data', 'alphasift', 'snapshot.last_good.json')));
});

test('desktop update backup list preserves the daily provider cache', (t) => {
  const mainModule = loadMainModule(t);
  const files = mainModule.DESKTOP_UPDATE_RUNTIME_RELATIVE_FILES || [];
  assert.ok(files.includes(path.join('data', 'provider_cache', 'daily')));
});

test('desktop update backup list preserves embedded Ollama models', (t) => {
  const mainModule = loadMainModule(t);
  const files = mainModule.DESKTOP_UPDATE_RUNTIME_RELATIVE_FILES || [];
  assert.ok(files.includes(path.join('data', 'ollama', 'models')));
});

test('desktop update backup and restore preserve generation backend env keys', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-env-backup-'));
  const appDir = path.join(tempRoot, 'app');
  const userDataDir = path.join(tempRoot, 'userData');
  const backupRoot = path.join(userDataDir, '.dsa-desktop-update-backup');
  const envPath = path.join(appDir, '.env');
  const envContent = [
    'GENERATION_BACKEND=codex_cli',
    'GENERATION_FALLBACK_BACKEND=litellm',
    'CODEX_CLI_PRESET=codex',
    'AGENT_GENERATION_BACKEND=codex_cli',
    '',
  ].join('\n');
  let currentVersion = '3.12.0';

  fs.mkdirSync(appDir, { recursive: true });
  fs.mkdirSync(userDataDir, { recursive: true });
  fs.writeFileSync(path.join(appDir, 'Uninstall Daily Stock Analysis.exe'), '');
  fs.writeFileSync(envPath, envContent, 'utf-8');

  const mainModule = loadMainModule(t, {
    platform: 'win32',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return path.join(appDir, 'Daily Stock Analysis.exe');
        }
        return userDataDir;
      },
      getVersion: () => currentVersion,
    },
  });

  t.after(() => {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  mainModule.backupPackagedRuntimeState();
  assert.equal(fs.readFileSync(path.join(backupRoot, '.env'), 'utf-8'), envContent);
  assert.ok(JSON.parse(fs.readFileSync(path.join(backupRoot, 'runtime-state.json'), 'utf-8')).files.includes('.env'));

  fs.writeFileSync(envPath, 'GENERATION_BACKEND=litellm\n', 'utf-8');
  currentVersion = '3.13.0';
  const restoreResult = mainModule.restorePackagedRuntimeStateFromBackup();

  assert.deepEqual(restoreResult.failed, []);
  assert.ok(restoreResult.restored.includes('.env'));
  assert.equal(fs.readFileSync(envPath, 'utf-8'), envContent);
  assert.equal(fs.existsSync(backupRoot), false);
});

test('desktop update backup and restore preserve AlphaSift detail directories recursively', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-dir-backup-'));
  const appDir = path.join(tempRoot, 'app');
  const userDataDir = path.join(tempRoot, 'userData');
  const backupRoot = path.join(userDataDir, '.dsa-desktop-update-backup');
  const detailRelativePath = path.join('data', 'alphasift', 'hotspot_details');
  const topicDetailPath = path.join(appDir, detailRelativePath, 'AI算力', 'detail.json');
  const nestedDetailPath = path.join(appDir, detailRelativePath, 'AI算力', 'events', 'latest.json');
  let currentVersion = '3.12.0';

  fs.mkdirSync(path.dirname(nestedDetailPath), { recursive: true });
  fs.mkdirSync(userDataDir, { recursive: true });
  fs.writeFileSync(path.join(appDir, 'Uninstall Daily Stock Analysis.exe'), '');
  fs.writeFileSync(topicDetailPath, '{"topic":"AI算力"}\n', 'utf-8');
  fs.writeFileSync(nestedDetailPath, '{"events":1}\n', 'utf-8');

  const mainModule = loadMainModule(t, {
    platform: 'win32',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return path.join(appDir, 'Daily Stock Analysis.exe');
        }
        return userDataDir;
      },
      getVersion: () => currentVersion,
    },
  });

  t.after(() => {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  mainModule.backupPackagedRuntimeState();
  assert.equal(fs.readFileSync(path.join(backupRoot, detailRelativePath, 'AI算力', 'detail.json'), 'utf-8'), '{"topic":"AI算力"}\n');
  assert.equal(fs.readFileSync(path.join(backupRoot, detailRelativePath, 'AI算力', 'events', 'latest.json'), 'utf-8'), '{"events":1}\n');
  assert.ok(
    JSON.parse(fs.readFileSync(path.join(backupRoot, 'runtime-state.json'), 'utf-8')).files.includes(detailRelativePath)
  );

  fs.rmSync(path.join(appDir, detailRelativePath), { recursive: true, force: true });
  currentVersion = '3.13.0';
  const restoreResult = mainModule.restorePackagedRuntimeStateFromBackup();

  assert.deepEqual(restoreResult.failed, []);
  assert.ok(restoreResult.restored.includes(detailRelativePath));
  assert.equal(fs.readFileSync(topicDetailPath, 'utf-8'), '{"topic":"AI算力"}\n');
  assert.equal(fs.readFileSync(nestedDetailPath, 'utf-8'), '{"events":1}\n');
  assert.equal(fs.existsSync(backupRoot), false);
});

test('StockPulse migration copies legacy user data without overwriting or deleting the rollback source', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-brand-migrate-'));
  const legacyUserDataDir = path.join(tempRoot, 'Daily Stock Analysis');
  const currentUserDataDir = path.join(tempRoot, 'StockPulse');
  const legacyDatabase = path.join(legacyUserDataDir, 'data', 'stock_analysis.db');
  const legacyLocalStorage = path.join(legacyUserDataDir, 'Local Storage', 'leveldb', '000003.log');
  const currentEnv = path.join(currentUserDataDir, '.env');

  fs.mkdirSync(path.dirname(legacyDatabase), { recursive: true });
  fs.mkdirSync(path.dirname(legacyLocalStorage), { recursive: true });
  fs.mkdirSync(currentUserDataDir, { recursive: true });
  fs.writeFileSync(path.join(legacyUserDataDir, '.env'), 'OPENAI_API_KEY=legacy\n', 'utf-8');
  fs.writeFileSync(legacyDatabase, 'legacy-db');
  fs.writeFileSync(legacyLocalStorage, 'legacy-browser-state');
  fs.writeFileSync(currentEnv, 'OPENAI_API_KEY=current\n', 'utf-8');

  const mainModule = loadMainModule(t, {
    platform: 'darwin',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return path.join(tempRoot, 'StockPulse.app', 'Contents', 'MacOS', 'StockPulse');
        }
        return currentUserDataDir;
      },
    },
  });

  t.after(() => {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  assert.equal(fs.readFileSync(currentEnv, 'utf-8'), 'OPENAI_API_KEY=current\n');
  assert.equal(
    fs.readFileSync(path.join(currentUserDataDir, 'data', 'stock_analysis.db'), 'utf-8'),
    'legacy-db'
  );
  assert.equal(
    fs.readFileSync(path.join(currentUserDataDir, 'Local Storage', 'leveldb', '000003.log'), 'utf-8'),
    'legacy-browser-state'
  );
  assert.equal(fs.readFileSync(legacyDatabase, 'utf-8'), 'legacy-db');
  assert.equal(fs.readFileSync(path.join(legacyUserDataDir, '.env'), 'utf-8'), 'OPENAI_API_KEY=legacy\n');

  const recordPath = path.join(currentUserDataDir, '.stockpulse-brand-migration.json');
  const record = JSON.parse(fs.readFileSync(recordPath, 'utf-8'));
  assert.equal(record.status, 'completed');
  assert.equal(record.sourceDir, legacyUserDataDir);
  assert.equal(record.targetDir, currentUserDataDir);
  assert.equal(record.sourcePreservedForRollback, true);
  assert.ok(record.skipped.includes('.env'));

  const secondRun = mainModule.migrateLegacyProductUserData();
  assert.equal(secondRun.alreadyCompleted, true);
  assert.deepEqual(secondRun.migrated, []);
});

test('StockPulse migration falls back to the legacy directory when critical data cannot be copied', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-brand-fallback-'));
  const legacyUserDataDir = path.join(tempRoot, 'Daily Stock Analysis');
  const currentUserDataDir = path.join(tempRoot, 'StockPulse');
  const legacyEnv = path.join(legacyUserDataDir, '.env');
  const currentEnv = path.join(currentUserDataDir, '.env');
  const legacyDatabase = path.join(legacyUserDataDir, 'data', 'stock_analysis.db');
  const currentDatabase = path.join(currentUserDataDir, 'data', 'stock_analysis.db');
  const originalCopyFileSync = fs.copyFileSync;
  let activeUserDataDir = currentUserDataDir;

  fs.mkdirSync(path.dirname(legacyDatabase), { recursive: true });
  fs.writeFileSync(legacyEnv, 'MIGRATION_VALUE=before-fallback\n', 'utf-8');
  fs.writeFileSync(legacyDatabase, 'legacy-db');
  fs.copyFileSync = (source, target, mode) => {
    if (source === legacyDatabase) {
      fs.writeFileSync(target, 'interrupted-partial-copy');
      throw new Error('copy interrupted after destination write');
    }
    return originalCopyFileSync(source, target, mode);
  };

  const mainModule = loadMainModule(t, {
    platform: 'darwin',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return path.join(tempRoot, 'StockPulse.app', 'Contents', 'MacOS', 'StockPulse');
        }
        return activeUserDataDir;
      },
      setPath: (name, value) => {
        if (name === 'userData') {
          activeUserDataDir = value;
        }
      },
    },
  });

  t.after(() => {
    fs.copyFileSync = originalCopyFileSync;
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  assert.equal(mainModule.resolveAppDir(), legacyUserDataDir);
  assert.equal(fs.existsSync(currentEnv), false);
  assert.equal(fs.readFileSync(legacyDatabase, 'utf-8'), 'legacy-db');
  assert.equal(fs.existsSync(currentDatabase), false);
  assert.deepEqual(fs.readdirSync(path.dirname(currentDatabase)), []);
  const record = JSON.parse(
    fs.readFileSync(path.join(currentUserDataDir, '.stockpulse-brand-migration.json'), 'utf-8')
  );
  assert.equal(record.status, 'incomplete');
  assert.match(record.failed.join('\n'), /copy interrupted after destination write/);
  assert.deepEqual(record.rollbackFailed, []);

  fs.copyFileSync = originalCopyFileSync;
  fs.writeFileSync(legacyEnv, 'MIGRATION_VALUE=after-fallback\n', 'utf-8');
  fs.writeFileSync(legacyDatabase, 'legacy-db-after-fallback');
  const retryResult = mainModule.migrateLegacyProductUserData({
    currentUserDataDir,
    legacyUserDataDirs: [legacyUserDataDir],
  });
  assert.equal(retryResult.completed, true);
  assert.equal(fs.readFileSync(currentEnv, 'utf-8'), 'MIGRATION_VALUE=after-fallback\n');
  assert.equal(fs.readFileSync(currentDatabase, 'utf-8'), 'legacy-db-after-fallback');
});

test('StockPulse migration treats a root data type conflict as a critical fallback', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-brand-root-conflict-'));
  const legacyUserDataDir = path.join(tempRoot, 'Daily Stock Analysis');
  const currentUserDataDir = path.join(tempRoot, 'StockPulse');
  const legacyDatabase = path.join(legacyUserDataDir, 'data', 'stock_analysis.db');
  let activeUserDataDir = currentUserDataDir;

  fs.mkdirSync(path.dirname(legacyDatabase), { recursive: true });
  fs.mkdirSync(currentUserDataDir, { recursive: true });
  fs.writeFileSync(legacyDatabase, 'legacy-db');
  fs.writeFileSync(path.join(currentUserDataDir, 'data'), 'not-a-directory');

  const mainModule = loadMainModule(t, {
    platform: 'darwin',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return path.join(tempRoot, 'StockPulse.app', 'Contents', 'MacOS', 'StockPulse');
        }
        return activeUserDataDir;
      },
      setPath: (name, value) => {
        if (name === 'userData') {
          activeUserDataDir = value;
        }
      },
    },
  });

  t.after(() => {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  assert.equal(mainModule.resolveAppDir(), legacyUserDataDir);
  const record = JSON.parse(
    fs.readFileSync(path.join(currentUserDataDir, '.stockpulse-brand-migration.json'), 'utf-8')
  );
  assert.equal(record.status, 'incomplete');
  assert.equal(record.usingLegacyFallback, true);
  assert.match(record.failed.join('\n'), /data \(target type differs\)/);
});

test('StockPulse critical fallback preserves pre-existing target state without mixing snapshots', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-brand-existing-target-'));
  const legacyUserDataDir = path.join(tempRoot, 'Daily Stock Analysis');
  const currentUserDataDir = path.join(tempRoot, 'StockPulse');
  const legacyDatabase = path.join(legacyUserDataDir, 'data', 'stock_analysis.db');
  const legacyAdditionalData = path.join(legacyUserDataDir, 'data', 'pending-copy.db');
  const currentDatabase = path.join(currentUserDataDir, 'data', 'stock_analysis.db');
  const originalCopyFileSync = fs.copyFileSync;
  let activeUserDataDir = currentUserDataDir;

  fs.mkdirSync(path.dirname(legacyDatabase), { recursive: true });
  fs.mkdirSync(path.dirname(currentDatabase), { recursive: true });
  fs.writeFileSync(legacyDatabase, 'legacy-db');
  fs.writeFileSync(legacyAdditionalData, 'legacy-pending-copy');
  fs.writeFileSync(currentDatabase, 'newer-stockpulse-db');
  fs.copyFileSync = (source, target, mode) => {
    if (source === legacyAdditionalData) {
      throw new Error('pending data cannot be copied');
    }
    return originalCopyFileSync(source, target, mode);
  };

  loadMainModule(t, {
    platform: 'darwin',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return path.join(tempRoot, 'StockPulse.app', 'Contents', 'MacOS', 'StockPulse');
        }
        return activeUserDataDir;
      },
      setPath: (name, value) => {
        if (name === 'userData') {
          activeUserDataDir = value;
        }
      },
    },
  });

  t.after(() => {
    fs.copyFileSync = originalCopyFileSync;
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  assert.equal(activeUserDataDir, legacyUserDataDir);
  assert.equal(fs.readFileSync(currentDatabase, 'utf-8'), 'newer-stockpulse-db');
  assert.equal(fs.existsSync(path.join(currentUserDataDir, 'data', 'pending-copy.db')), false);
  const record = JSON.parse(
    fs.readFileSync(path.join(currentUserDataDir, '.stockpulse-brand-migration.json'), 'utf-8')
  );
  assert.equal(record.usingLegacyFallback, true);
  assert.match(record.failed.join('\n'), /pending data cannot be copied/);
});

test('packaged StockPulse exits before migration when another instance owns the lock', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-brand-instance-lock-'));
  const legacyUserDataDir = path.join(tempRoot, 'Daily Stock Analysis');
  const currentUserDataDir = path.join(tempRoot, 'StockPulse');
  const lifecycle = [];

  fs.mkdirSync(path.join(legacyUserDataDir, 'data'), { recursive: true });
  fs.writeFileSync(path.join(legacyUserDataDir, 'data', 'stock_analysis.db'), 'legacy-db');

  loadMainModule(t, {
    platform: 'darwin',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return path.join(tempRoot, 'StockPulse.app', 'Contents', 'MacOS', 'StockPulse');
        }
        return currentUserDataDir;
      },
      requestSingleInstanceLock: () => {
        lifecycle.push('lock');
        return false;
      },
      whenReady: () => {
        lifecycle.push('ready');
        return { then: () => undefined };
      },
      quit: () => {
        lifecycle.push('quit');
      },
    },
  });

  t.after(() => {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  assert.deepEqual(lifecycle, ['lock', 'quit']);
  assert.equal(fs.existsSync(currentUserDataDir), false);
});

test('StockPulse upgrade restores a legacy updater backup and recognizes both uninstaller names', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-upgrade-smoke-'));
  const appDir = path.join(tempRoot, 'app');
  const currentUserDataDir = path.join(tempRoot, 'StockPulse');
  const legacyUserDataDir = path.join(tempRoot, 'Daily Stock Analysis');
  const legacyBackupRoot = path.join(legacyUserDataDir, '.dsa-desktop-update-backup');
  const currentUninstaller = path.join(appDir, 'Uninstall StockPulse.exe');
  const legacyUninstaller = path.join(appDir, 'Uninstall Daily Stock Analysis.exe');

  fs.mkdirSync(legacyBackupRoot, { recursive: true });
  fs.mkdirSync(appDir, { recursive: true });
  fs.writeFileSync(currentUninstaller, '');
  fs.writeFileSync(path.join(legacyBackupRoot, '.env'), 'PRESERVED_DURING_UPDATE=true\n', 'utf-8');
  fs.writeFileSync(
    path.join(legacyBackupRoot, 'runtime-state.json'),
    JSON.stringify({ appVersion: '3.20.0', files: ['.env'] }),
    'utf-8'
  );

  const mainModule = loadMainModule(t, {
    platform: 'win32',
    app: {
      isPackaged: true,
      getVersion: () => '3.21.0',
      getPath: (name) => {
        if (name === 'exe') {
          return path.join(appDir, 'StockPulse.exe');
        }
        return currentUserDataDir;
      },
    },
  });

  t.after(() => {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  assert.equal(mainModule.isWindowsNsisInstalledApp(), true);
  const restoreResult = mainModule.restorePackagedRuntimeStateFromBackup();
  assert.deepEqual(restoreResult.failed, []);
  assert.deepEqual(restoreResult.restored, ['.env']);
  assert.equal(
    fs.readFileSync(path.join(appDir, '.env'), 'utf-8'),
    'PRESERVED_DURING_UPDATE=true\n'
  );
  assert.equal(fs.existsSync(path.join(currentUserDataDir, '.dsa-desktop-update-backup')), false);
  assert.equal(fs.existsSync(legacyBackupRoot), true);
  assert.equal(fs.existsSync(path.join(currentUserDataDir, '.stockpulse-brand-migration.json')), true);

  fs.rmSync(currentUninstaller);
  fs.writeFileSync(legacyUninstaller, '');
  assert.equal(mainModule.isWindowsNsisInstalledApp(), true);
});

test('macOS packaged runtime state uses userData and migrates old app bundle files', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-macos-migrate-'));
  const oldAppDir = path.join(tempRoot, 'Daily Stock Analysis.app', 'Contents', 'MacOS');
  const userDataDir = path.join(tempRoot, 'userData');
  const exePath = path.join(oldAppDir, 'Daily Stock Analysis');
  const oldDbPath = path.join(oldAppDir, 'data', 'stock_analysis.db');
  const oldLogPath = path.join(oldAppDir, 'logs', 'desktop.log');
  const oldHotspotDetailPath = path.join(oldAppDir, 'data', 'alphasift', 'hotspot_details', 'AI算力', 'detail.json');

  fs.mkdirSync(path.dirname(oldDbPath), { recursive: true });
  fs.mkdirSync(path.dirname(oldLogPath), { recursive: true });
  fs.mkdirSync(path.dirname(oldHotspotDetailPath), { recursive: true });
  fs.mkdirSync(userDataDir, { recursive: true });
  fs.writeFileSync(exePath, '');
  fs.writeFileSync(path.join(oldAppDir, '.env'), 'OPENAI_API_KEY=old-key\n', 'utf-8');
  fs.writeFileSync(oldDbPath, 'old-db');
  fs.writeFileSync(oldLogPath, 'old-log\n', 'utf-8');
  fs.writeFileSync(oldHotspotDetailPath, '{"topic":"AI算力"}\n', 'utf-8');

  const mainModule = loadMainModule(t, {
    platform: 'darwin',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return exePath;
        }
        return userDataDir;
      },
    },
  });

  t.after(() => {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  const migrationResult = mainModule.migrateMacPackagedRuntimeState();
  assert.equal(mainModule.resolveAppDir(), userDataDir);
  assert.deepEqual(migrationResult.failed, []);
  assert.deepEqual(
    [...migrationResult.migrated].sort(),
    [
      '.env',
      path.join('data', 'stock_analysis.db'),
      path.join('data', 'alphasift', 'hotspot_details'),
      path.join('logs', 'desktop.log'),
    ].sort()
  );
  assert.equal(fs.readFileSync(path.join(userDataDir, '.env'), 'utf-8'), 'OPENAI_API_KEY=old-key\n');
  assert.equal(fs.readFileSync(path.join(userDataDir, 'data', 'stock_analysis.db'), 'utf-8'), 'old-db');
  assert.equal(
    fs.readFileSync(path.join(userDataDir, 'data', 'alphasift', 'hotspot_details', 'AI算力', 'detail.json'), 'utf-8'),
    '{"topic":"AI算力"}\n'
  );
  assert.equal(fs.readFileSync(path.join(userDataDir, 'logs', 'desktop.log'), 'utf-8'), 'old-log\n');
});

test('macOS runtime migration does not overwrite existing userData files', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-macos-skip-'));
  const oldAppDir = path.join(tempRoot, 'Daily Stock Analysis.app', 'Contents', 'MacOS');
  const userDataDir = path.join(tempRoot, 'userData');
  const exePath = path.join(oldAppDir, 'Daily Stock Analysis');

  fs.mkdirSync(oldAppDir, { recursive: true });
  fs.mkdirSync(userDataDir, { recursive: true });
  fs.writeFileSync(exePath, '');
  fs.writeFileSync(path.join(oldAppDir, '.env'), 'OPENAI_API_KEY=old-key\n', 'utf-8');
  fs.writeFileSync(path.join(userDataDir, '.env'), 'OPENAI_API_KEY=new-key\n', 'utf-8');

  const mainModule = loadMainModule(t, {
    platform: 'darwin',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return exePath;
        }
        return userDataDir;
      },
    },
  });

  t.after(() => {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  const migrationResult = mainModule.migrateMacPackagedRuntimeState();
  assert.deepEqual(migrationResult.migrated, []);
  assert.deepEqual(migrationResult.failed, []);
  assert.deepEqual(migrationResult.skipped, ['.env']);
  assert.equal(fs.readFileSync(path.join(userDataDir, '.env'), 'utf-8'), 'OPENAI_API_KEY=new-key\n');
});

test('macOS runtime migration discovers a sibling legacy app bundle after the product rename', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-macos-legacy-bundle-'));
  const applicationsDir = path.join(tempRoot, 'Applications');
  const currentAppDir = path.join(applicationsDir, 'StockPulse.app', 'Contents', 'MacOS');
  const legacyAppDir = path.join(applicationsDir, 'Daily Stock Analysis.app', 'Contents', 'MacOS');
  const currentExePath = path.join(currentAppDir, 'StockPulse');
  const legacyDatabase = path.join(legacyAppDir, 'data', 'stock_analysis.db');
  const userDataDir = path.join(tempRoot, 'Application Support', 'StockPulse');

  fs.mkdirSync(currentAppDir, { recursive: true });
  fs.mkdirSync(path.dirname(legacyDatabase), { recursive: true });
  fs.mkdirSync(userDataDir, { recursive: true });
  fs.writeFileSync(currentExePath, '');
  fs.writeFileSync(path.join(legacyAppDir, '.env'), 'OPENAI_API_KEY=legacy-bundle\n', 'utf-8');
  fs.writeFileSync(legacyDatabase, 'legacy-bundle-db');

  const mainModule = loadMainModule(t, {
    platform: 'darwin',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return currentExePath;
        }
        return userDataDir;
      },
    },
  });

  t.after(() => {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  const migrationResult = mainModule.migrateMacPackagedRuntimeState();
  assert.deepEqual(migrationResult.failed, []);
  assert.ok(migrationResult.sourceDirs.includes(legacyAppDir));
  assert.ok(migrationResult.migrated.includes('.env'));
  assert.ok(migrationResult.migrated.includes(path.join('data', 'stock_analysis.db')));
  assert.equal(
    fs.readFileSync(path.join(userDataDir, '.env'), 'utf-8'),
    'OPENAI_API_KEY=legacy-bundle\n'
  );
  assert.equal(
    fs.readFileSync(path.join(userDataDir, 'data', 'stock_analysis.db'), 'utf-8'),
    'legacy-bundle-db'
  );
  assert.equal(fs.readFileSync(legacyDatabase, 'utf-8'), 'legacy-bundle-db');
});

test('restorePackagedRuntimeStateFromBackup keeps backup when copy fails', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-restore-'));
  const appDir = path.join(tempRoot, 'app');
  const userDataDir = path.join(tempRoot, 'userData');
  const backupRoot = path.join(userDataDir, '.dsa-desktop-update-backup');
  const backupDbPath = path.join(backupRoot, 'data', 'stock_analysis.db');
  fs.mkdirSync(path.dirname(backupDbPath), { recursive: true });
  fs.mkdirSync(appDir, { recursive: true });
  fs.writeFileSync(path.join(appDir, 'Uninstall Daily Stock Analysis.exe'), '');
  fs.writeFileSync(backupDbPath, 'backup-db');
  fs.writeFileSync(
    path.join(backupRoot, 'runtime-state.json'),
    JSON.stringify({ files: [path.join('data', 'stock_analysis.db')] }),
    'utf-8'
  );

  const mainModule = loadMainModule(t, {
    platform: 'win32',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return path.join(appDir, 'Daily Stock Analysis.exe');
        }
        return userDataDir;
      },
    },
  });
  const originalCopyFileSync = fs.copyFileSync;
  let failedCopyAttempted = false;

  fs.copyFileSync = (source, target) => {
    if (source === backupDbPath) {
      failedCopyAttempted = true;
      throw new Error('target locked');
    }
    return originalCopyFileSync(source, target);
  };

  t.after(() => {
    fs.copyFileSync = originalCopyFileSync;
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  const restoreResult = mainModule.restorePackagedRuntimeStateFromBackup();
  assert.equal(failedCopyAttempted, true);
  assert.equal(Array.isArray(restoreResult.failed), true);
  assert.equal(restoreResult.failed.length > 0, true);
  assert.equal(fs.existsSync(backupRoot), true);
  assert.equal(fs.existsSync(path.join(backupRoot, 'runtime-state.json')), true);
  assert.equal(restoreResult.failed[0].includes('target locked'), true);
});

test('restorePackagedRuntimeStateFromBackup removes restored files from pending manifest', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-partial-restore-'));
  const appDir = path.join(tempRoot, 'app');
  const userDataDir = path.join(tempRoot, 'userData');
  const backupRoot = path.join(userDataDir, '.dsa-desktop-update-backup');
  const backupEnvPath = path.join(backupRoot, '.env');
  const backupDbPath = path.join(backupRoot, 'data', 'stock_analysis.db');
  const targetEnvPath = path.join(appDir, '.env');
  const manifestPath = path.join(backupRoot, 'runtime-state.json');
  const dbRelativePath = path.join('data', 'stock_analysis.db');

  fs.mkdirSync(path.dirname(backupDbPath), { recursive: true });
  fs.mkdirSync(appDir, { recursive: true });
  fs.writeFileSync(path.join(appDir, 'Uninstall Daily Stock Analysis.exe'), '');
  fs.writeFileSync(backupEnvPath, 'backup-env\n', 'utf-8');
  fs.writeFileSync(backupDbPath, 'backup-db');
  fs.writeFileSync(targetEnvPath, 'current-env\n', 'utf-8');
  fs.writeFileSync(
    manifestPath,
    JSON.stringify({ files: ['.env', dbRelativePath] }),
    'utf-8'
  );

  const mainModule = loadMainModule(t, {
    platform: 'win32',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return path.join(appDir, 'Daily Stock Analysis.exe');
        }
        return userDataDir;
      },
    },
  });
  const originalCopyFileSync = fs.copyFileSync;

  fs.copyFileSync = (source, target) => {
    if (source === backupDbPath) {
      throw new Error('target locked');
    }
    return originalCopyFileSync(source, target);
  };

  t.after(() => {
    fs.copyFileSync = originalCopyFileSync;
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  const firstRestore = mainModule.restorePackagedRuntimeStateFromBackup();
  assert.deepEqual(firstRestore.restored, ['.env']);
  assert.equal(firstRestore.failed.length, 1);
  assert.equal(fs.readFileSync(targetEnvPath, 'utf-8'), 'backup-env\n');
  assert.deepEqual(JSON.parse(fs.readFileSync(manifestPath, 'utf-8')).files, [dbRelativePath]);

  fs.writeFileSync(targetEnvPath, 'user-change-after-partial-failure\n', 'utf-8');
  const secondRestore = mainModule.restorePackagedRuntimeStateFromBackup();
  assert.deepEqual(secondRestore.restored, []);
  assert.equal(secondRestore.failed.length, 1);
  assert.equal(fs.readFileSync(targetEnvPath, 'utf-8'), 'user-change-after-partial-failure\n');
  assert.deepEqual(JSON.parse(fs.readFileSync(manifestPath, 'utf-8')).files, [dbRelativePath]);
});

test('restorePackagedRuntimeStateFromBackup skips backup when app version did not change', (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-same-version-restore-'));
  const appDir = path.join(tempRoot, 'app');
  const userDataDir = path.join(tempRoot, 'userData');
  const backupRoot = path.join(userDataDir, '.dsa-desktop-update-backup');
  const backupEnvPath = path.join(backupRoot, '.env');
  const targetEnvPath = path.join(appDir, '.env');
  const manifestPath = path.join(backupRoot, 'runtime-state.json');

  fs.mkdirSync(backupRoot, { recursive: true });
  fs.mkdirSync(appDir, { recursive: true });
  fs.writeFileSync(path.join(appDir, 'Uninstall Daily Stock Analysis.exe'), '');
  fs.writeFileSync(backupEnvPath, 'pre-update-env\n', 'utf-8');
  fs.writeFileSync(targetEnvPath, 'user-change-after-aborted-install\n', 'utf-8');
  fs.writeFileSync(
    manifestPath,
    JSON.stringify({ appVersion: 'v3.12.0', files: ['.env'] }),
    'utf-8'
  );

  const mainModule = loadMainModule(t, {
    platform: 'win32',
    app: {
      isPackaged: true,
      getPath: (name) => {
        if (name === 'exe') {
          return path.join(appDir, 'Daily Stock Analysis.exe');
        }
        return userDataDir;
      },
    },
  });

  t.after(() => {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });

  const restoreResult = mainModule.restorePackagedRuntimeStateFromBackup();
  assert.deepEqual(restoreResult.restored, []);
  assert.deepEqual(restoreResult.failed, []);
  assert.equal(restoreResult.skipped.length, 1);
  assert.match(restoreResult.skipped[0], /stale backup target 3\.12\.0 was discarded/);
  assert.equal(fs.readFileSync(targetEnvPath, 'utf-8'), 'user-change-after-aborted-install\n');
  assert.equal(fs.existsSync(backupRoot), false);
  assert.equal(fs.existsSync(manifestPath), false);
});

test('createWindow startup routes a pending deep link after restore and backend readiness', async (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-desktop-startup-'));
  const appDir = path.join(tempRoot, 'app');
  const userDataDir = path.join(tempRoot, 'userData');
  const exePath = path.join(appDir, 'Daily Stock Analysis.exe');
  const uninstallPath = path.join(appDir, 'Uninstall Daily Stock Analysis.exe');
  const loadedFiles = [];
  const loadedUrls = [];
  let startupError;
  let updateCheckRequested = false;
  const originalResourcesPathDescriptor = Object.getOwnPropertyDescriptor(process, 'resourcesPath');
  const resourcesPath = path.join(tempRoot, 'resources');
  const backupRoot = path.join(userDataDir, '.dsa-desktop-update-backup');
  const manifestPath = path.join(backupRoot, 'runtime-state.json');

  function fakeBrowserWindow() {
    return {
      isDestroyed: () => false,
      setBackgroundColor: () => undefined,
      once: () => undefined,
      webContents: {
        on: () => undefined,
        setWindowOpenHandler: () => undefined,
        send: () => undefined,
      },
      loadFile: async (file) => {
        loadedFiles.push(file);
        return undefined;
      },
      loadURL: async (url) => {
        loadedUrls.push(url);
        return undefined;
      },
    };
  }

  const fakeBackendProcess = new EventEmitter();
  fakeBackendProcess.pid = 12345;
  fakeBackendProcess.exitCode = null;
  fakeBackendProcess.signalCode = null;
  fakeBackendProcess.stdout = new EventEmitter();
  fakeBackendProcess.stderr = new EventEmitter();

  const fakeWhenReady = () => ({
    then: (handler) => {
      return Promise.resolve()
        .then(() => handler())
        .catch((error) => {
          startupError = error;
        });
    },
  });

  const fakeNet = {
    createServer: () => {
      const server = new EventEmitter();
      server.once = (event, handler) => {
        server.on(event, handler);
        return server;
      };
      server.listen = () => {
        process.nextTick(() => {
          server.emit('listening');
        });
        return server;
      };
      server.close = (callback) => {
        if (callback) {
          process.nextTick(callback);
        }
      };
      return server;
    },
  };

  const fakeHttp = {
    get: (_url, onResponse) => {
      const request = new EventEmitter();
      const response = new EventEmitter();
      request.setTimeout = () => undefined;
      request.destroy = () => undefined;
      response.statusCode = 200;
      response.resume = () => undefined;
      process.nextTick(() => {
        onResponse(response);
      });
      return request;
    },
  };

  if (originalResourcesPathDescriptor) {
    Object.defineProperty(process, 'resourcesPath', {
      ...originalResourcesPathDescriptor,
      value: resourcesPath,
    });
  } else {
    process.resourcesPath = resourcesPath;
  }

  fs.mkdirSync(appDir, { recursive: true });
  fs.mkdirSync(userDataDir, { recursive: true });
  fs.mkdirSync(backupRoot, { recursive: true });
  fs.mkdirSync(path.join(resourcesPath, 'backend', 'stock_analysis'), { recursive: true });
  fs.writeFileSync(exePath, '');
  fs.writeFileSync(uninstallPath, '');
  fs.writeFileSync(path.join(backupRoot, '.env'), 'stale-backup-env\n', 'utf-8');
  fs.writeFileSync(manifestPath, JSON.stringify({ appVersion: '3.12.0', files: ['.env'] }), 'utf-8');
  fs.writeFileSync(path.join(resourcesPath, 'backend', 'stock_analysis', 'stock_analysis.exe'), '');

  const mainModule = loadMainModule(t, {
    platform: 'win32',
    browserWindow: fakeBrowserWindow,
    http: fakeHttp,
    net: fakeNet,
    childProcess: {
      spawn: () => fakeBackendProcess,
    },
    app: {
      isPackaged: true,
      getVersion: () => '3.12.0',
      getPath: (name) => {
        if (name === 'exe') {
          return exePath;
        }
        return userDataDir;
      },
      whenReady: fakeWhenReady,
      on: () => undefined,
      quit: () => undefined,
    },
    electronUpdater: {
      autoDownload: true,
      autoInstallOnAppQuit: false,
      on: () => undefined,
      checkForUpdates: async () => {
        updateCheckRequested = true;
        return undefined;
      },
    },
  });
  assert.equal(mainModule.queueDesktopDeepLink('stockpulse://app/portfolio?account=7'), true);

  await new Promise((resolve) => {
    setTimeout(resolve, 80);
  });

  assert.equal(loadedFiles.length >= 1, true);
  assert.equal(loadedUrls.length >= 1, true);
  const loadedMainPageUrl = new URL(loadedUrls[0]);
  assert.match(loadedMainPageUrl.origin, /^http:\/\/127\.0\.0\.1:\d+$/);
  assert.equal(loadedMainPageUrl.pathname, '/portfolio');
  assert.equal(loadedMainPageUrl.searchParams.get('account'), '7');
  assert.equal(loadedMainPageUrl.searchParams.get('desktop_version'), '3.12.0');
  assert.match(loadedMainPageUrl.searchParams.get('cache_bust'), /^\d+$/);
  assert.equal(updateCheckRequested, true);
  assert.equal(startupError, undefined);
  assert.equal(fs.existsSync(backupRoot), false);
  const updateState = await mainModule.__getIpcMainHandler('desktop:get-update-state')();
  assert.notEqual(updateState.status, mainModule.UPDATE_STATUS.ERROR);
  assert.equal(updateState.updateMode, mainModule.UPDATE_MODE.AUTO);

  t.after(() => {
    if (originalResourcesPathDescriptor) {
      Object.defineProperty(process, 'resourcesPath', originalResourcesPathDescriptor);
    } else {
      delete process.resourcesPath;
    }
    fs.rmSync(tempRoot, { recursive: true, force: true });
  });
});

test('stopBackend waits for backend process exit', async (t) => {
  const mainModule = loadMainModule(t, { platform: 'linux' });
  const killSignals = [];
  const fakeBackend = new EventEmitter();

  fakeBackend.pid = 4321;
  fakeBackend.killed = false;
  fakeBackend.exitCode = null;
  fakeBackend.signalCode = null;
  fakeBackend.kill = (signal) => {
    killSignals.push(signal);
    fakeBackend.killed = true;
    if (signal === 'SIGTERM' || signal === 'SIGKILL') {
      process.nextTick(() => {
        fakeBackend.exitCode = 0;
        fakeBackend.emit('exit', 0, null);
      });
    }
  };

  mainModule.__setBackendProcessForTest(fakeBackend);

  t.after(() => {
    mainModule.__setBackendProcessForTest(null);
  });

  await Promise.race([
    mainModule.stopBackend(),
    new Promise((_, reject) => setTimeout(() => reject(new Error('stopBackend did not resolve')), 200)),
  ]);

  assert.equal(killSignals.includes('SIGTERM'), true);
  assert.equal(mainModule.__getBackendProcessForTest(), null);
});

test('stopBackend keeps backend process reference when exit wait times out', async (t) => {
  const mainModule = loadMainModule(t, { platform: 'linux' });
  const originalSetTimeout = global.setTimeout;
  const killSignals = [];
  const fakeBackend = new EventEmitter();

  fakeBackend.pid = 4321;
  fakeBackend.killed = false;
  fakeBackend.exitCode = null;
  fakeBackend.signalCode = null;
  fakeBackend.kill = (signal) => {
    killSignals.push(signal);
    fakeBackend.killed = true;
  };

  global.setTimeout = (callback, delay, ...args) => (
    originalSetTimeout(callback, delay >= 3000 ? 0 : delay, ...args)
  );
  mainModule.__setBackendProcessForTest(fakeBackend);

  t.after(() => {
    global.setTimeout = originalSetTimeout;
    mainModule.__setBackendProcessForTest(null);
  });

  await Promise.race([
    mainModule.stopBackend(),
    new Promise((_, reject) => originalSetTimeout(() => reject(new Error('stopBackend did not resolve')), 200)),
  ]);

  assert.equal(killSignals.includes('SIGTERM'), true);
  assert.equal(mainModule.__getBackendProcessForTest(), fakeBackend);
});

test('stopBackend uses taskkill on Windows and clears after backend exit', async (t) => {
  const taskkillCalls = [];
  const fakeBackend = new EventEmitter();
  const fakeTaskkill = new EventEmitter();
  const mainModule = loadMainModule(t, {
    platform: 'win32',
    childProcess: {
      spawn: (command, args, options) => {
        taskkillCalls.push({ command, args, options });
        process.nextTick(() => {
          fakeBackend.exitCode = 0;
          fakeBackend.emit('exit', 0, null);
          fakeTaskkill.emit('exit', 0, null);
        });
        return fakeTaskkill;
      },
    },
  });

  fakeBackend.pid = 4321;
  fakeBackend.killed = false;
  fakeBackend.exitCode = null;
  fakeBackend.signalCode = null;
  fakeBackend.kill = () => {
    throw new Error('Windows stopBackend should use taskkill instead of process.kill');
  };

  mainModule.__setBackendProcessForTest(fakeBackend);

  t.after(() => {
    mainModule.__setBackendProcessForTest(null);
  });

  await Promise.race([
    mainModule.stopBackend(),
    new Promise((_, reject) => setTimeout(() => reject(new Error('stopBackend did not resolve')), 200)),
  ]);

  assert.deepEqual(taskkillCalls, [
    {
      command: 'taskkill',
      args: ['/PID', '4321', '/T', '/F'],
      options: { windowsHide: true },
    },
  ]);
  assert.equal(mainModule.__getBackendProcessForTest(), null);
});

// ===== Local model lifecycle (issue #203) =====

function makeStagedJsonRequest(stages) {
  let index = 0;
  const calls = [];
  const impl = (target, options, cb) => {
    const stage = stages[Math.min(index, stages.length - 1)];
    const call = { target, options, body: [], responseDestroyed: false };
    calls.push(call);
    index += 1;
    const req = new EventEmitter();
    req.setTimeout = () => req;
    req.write = (chunk) => {
      call.body.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk)));
      return true;
    };
    req.destroy = () => undefined;
    req.end = () => {
      setImmediate(() => {
        if (stage && stage.connectionError) {
          req.emit('error', new Error('ECONNREFUSED'));
          return;
        }
        const response = new EventEmitter();
        response.statusCode = (stage && stage.statusCode) || 200;
        response.setEncoding = () => undefined;
        response.resume = () => undefined;
        response.destroy = () => {
          call.responseDestroyed = true;
        };
        cb(response);
        setImmediate(() => {
          if (stage && stage.jsonBody != null) {
            response.emit('data', Buffer.from(JSON.stringify(stage.jsonBody)));
          }
          if (stage && Array.isArray(stage.ndjson)) {
            for (const line of stage.ndjson) {
              response.emit('data', `${JSON.stringify(line)}\n`);
            }
          }
          if (stage && Array.isArray(stage.rawChunks)) {
            for (const chunk of stage.rawChunks) {
              response.emit('data', chunk);
            }
          }
          response.emit('end');
        });
      });
    };
    return req;
  };
  impl.calls = calls;
  return impl;
}

function makeLocalModelSpawn(records, { serveStaysAlive = true } = {}) {
  return (command, args, options) => {
    const call = { command, args: Array.isArray(args) ? [...args] : args, options };
    records.push(call);
    const child = new EventEmitter();
    child.pid = 4242;
    child.exitCode = null;
    child.signalCode = null;
    child.killed = false;
    child.kill = () => {
      child.killed = true;
      child.exitCode = 0;
      return true;
    };
    if (Array.isArray(args) && args.includes('--version')) {
      setImmediate(() => {
        child.exitCode = 0;
        child.emit('exit', 0);
      });
    } else if (Array.isArray(args) && args.includes('serve') && !serveStaysAlive) {
      setImmediate(() => {
        child.exitCode = 1;
        child.emit('exit', 1);
      });
    }
    return child;
  };
}

function createEmbeddedRuntimeFixture(t, {
  platform = 'darwin',
  arch = 'arm64',
  omitRequiredPath = '',
  omitRuntimePath = '',
} = {}) {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-embedded-ollama-'));
  const rootDir = path.join(tmpDir, 'ollama');
  fs.mkdirSync(rootDir, { recursive: true });
  const binaryPath = platform === 'win32' ? 'ollama.exe' : 'ollama';
  const requiredPaths = platform === 'win32'
    ? ['ollama.exe', 'lib/ollama/llama-server.exe']
    : ['ollama', 'llama-server'];
  const dependencyPath = platform === 'win32'
    ? 'lib/ollama/libllama-server-impl.dll'
    : 'libllama-server-impl.dylib';
  const runtimePaths = [...requiredPaths, dependencyPath].sort();
  const fileSha256 = {};
  for (const relativePath of runtimePaths) {
    const content = `fixture:${relativePath}`;
    fileSha256[relativePath] = crypto.createHash('sha256').update(content).digest('hex');
    if (relativePath === omitRequiredPath || relativePath === omitRuntimePath) {
      continue;
    }
    const absolutePath = path.join(rootDir, relativePath);
    fs.mkdirSync(path.dirname(absolutePath), { recursive: true });
    fs.writeFileSync(absolutePath, content);
    if (platform === 'darwin') {
      fs.chmodSync(absolutePath, 0o755);
    }
  }
  fs.writeFileSync(path.join(rootDir, 'runtime-manifest.json'), JSON.stringify({
    schemaVersion: 2,
    runtime: 'ollama',
    version: 'v0.32.3',
    platform,
    architecture: arch,
    supportedArchitectures: platform === 'darwin' ? ['arm64', 'x64'] : ['x64'],
    binaryPath,
    requiredPaths,
    fileSha256,
    archive: {
      fileName: platform === 'darwin' ? 'ollama-darwin.tgz' : 'ollama-windows-amd64.zip',
      sizeBytes: 123,
      sha256: 'a'.repeat(64),
    },
  }));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  return {
    rootDir,
    command: path.join(rootDir, binaryPath),
    dependencyPath,
  };
}

function makeRuntimeAvailabilitySpawn(records, resolveExitCode) {
  return (command, args, options) => {
    records.push({ command, args: [...args], options });
    const child = new EventEmitter();
    child.pid = 8181;
    child.exitCode = null;
    child.signalCode = null;
    child.kill = () => {
      child.exitCode = 0;
      return true;
    };
    const exitCode = resolveExitCode(command, args);
    setImmediate(() => {
      if (exitCode === 'error') {
        child.emit('error', new Error('ENOENT'));
        return;
      }
      if (exitCode != null) {
        child.exitCode = exitCode;
        child.emit('exit', exitCode);
      }
    });
    return child;
  };
}

test('local model names accept curated tags and reject injection payloads', (t) => {
  const mainModule = loadMainModule(t);

  for (const valid of [
    'qwen3:8b',
    'gemma4:12b',
    'deepseek-r1:8b',
    'qwen2.5-coder:7b',
    'stockpulse/fin-r1-7b:q4_k_m',
  ]) {
    assert.equal(mainModule.normalizeLocalModelName(valid), valid);
  }
  assert.equal(mainModule.normalizeLocalModelName(' qwen3:8b '), 'qwen3:8b');

  for (const invalid of [
    '',
    '   ',
    'qwen3:8b; rm -rf /',
    'qwen3 8b',
    '../etc/passwd',
    'model$(whoami)',
    'foo//bar',
    'foo|bar',
    'foo&&bar',
    'a'.repeat(200),
  ]) {
    assert.equal(mainModule.normalizeLocalModelName(invalid), null);
  }
});

test('only curated presets are allowed for download', (t) => {
  const mainModule = loadMainModule(t);

  assert.equal(mainModule.isAllowedLocalModelPreset('qwen3:8b'), true);
  assert.equal(mainModule.isAllowedLocalModelPreset('gemma4:12b'), true);
  assert.equal(mainModule.isAllowedLocalModelPreset('llama3.2:3b'), false);
  assert.equal(mainModule.isAllowedLocalModelPreset('mistral:latest'), false);
  assert.equal(mainModule.isAllowedLocalModelPreset('qwen3:8b; ls'), false);
});

test('installed model names are parsed and sanitized from the tags payload', (t) => {
  const mainModule = loadMainModule(t);

  assert.deepEqual(
    mainModule.extractLocalModelNames({
      models: [
        { name: 'qwen3:8b' },
        { name: 'gemma4:12b' },
        { name: '../evil' },
        { name: '' },
        { name: 'qwen3:8b' },
      ],
    }),
    ['gemma4:12b', 'qwen3:8b']
  );
  assert.deepEqual(mainModule.extractLocalModelNames(null), []);
  assert.deepEqual(mainModule.extractLocalModelNames({ models: 'nope' }), []);
});

test('local model binary resolution prefers a working system install', async (t) => {
  const mainModule = loadMainModule(t);
  const embedded = createEmbeddedRuntimeFixture(t);
  const records = [];
  const logs = [];

  const resolved = await mainModule.resolveLocalModelBinary({
    embeddedRoot: embedded.rootDir,
    platform: 'darwin',
    arch: 'arm64',
    spawnImpl: makeRuntimeAvailabilitySpawn(records, () => 0),
    logImpl: (line) => logs.push(line),
  });

  assert.equal(resolved.source, mainModule.DESKTOP_LOCAL_MODEL_RUNTIME_SOURCE.SYSTEM);
  assert.equal(resolved.command, 'ollama');
  assert.deepEqual(records.map((record) => record.command), ['ollama']);
  assert.deepEqual(logs, ['[local-model] runtime resolution source=system']);
});

test('local model binary resolution falls back to a valid embedded runtime', async (t) => {
  const mainModule = loadMainModule(t);
  const embedded = createEmbeddedRuntimeFixture(t);
  const records = [];
  const logs = [];

  const resolved = await mainModule.resolveLocalModelBinary({
    embeddedRoot: embedded.rootDir,
    platform: 'darwin',
    arch: 'arm64',
    spawnImpl: makeRuntimeAvailabilitySpawn(
      records,
      (command) => command === 'ollama' ? 'error' : 0
    ),
    logImpl: (line) => logs.push(line),
  });

  assert.equal(resolved.source, mainModule.DESKTOP_LOCAL_MODEL_RUNTIME_SOURCE.EMBEDDED);
  assert.equal(resolved.command, embedded.command);
  assert.deepEqual(records.map((record) => record.command), ['ollama', embedded.command]);
  assert.ok(logs.some((line) => line.includes('source=embedded version=v0.32.3')));
  assert.ok(logs.every((line) => !line.includes(embedded.rootDir)));
});

test('local model binary resolution rejects missing and non-working embedded resources', async (t) => {
  const mainModule = loadMainModule(t);
  const incomplete = createEmbeddedRuntimeFixture(t, { omitRequiredPath: 'llama-server' });
  const incompleteRecords = [];
  const incompleteResult = await mainModule.resolveLocalModelBinary({
    embeddedRoot: incomplete.rootDir,
    platform: 'darwin',
    arch: 'arm64',
    spawnImpl: makeRuntimeAvailabilitySpawn(incompleteRecords, () => 'error'),
    logImpl: () => undefined,
  });
  assert.equal(incompleteResult, null);
  assert.deepEqual(incompleteRecords.map((record) => record.command), ['ollama']);

  const corrupt = createEmbeddedRuntimeFixture(t);
  const corruptRecords = [];
  const corruptResult = await mainModule.resolveLocalModelBinary({
    embeddedRoot: corrupt.rootDir,
    platform: 'darwin',
    arch: 'arm64',
    spawnImpl: makeRuntimeAvailabilitySpawn(
      corruptRecords,
      (command) => command === 'ollama' ? 'error' : 1
    ),
    logImpl: () => undefined,
  });
  assert.equal(corruptResult, null);
  assert.deepEqual(corruptRecords.map((record) => record.command), ['ollama', corrupt.command]);
});

test('local model binary resolution rejects an embedded runtime with corrupt helper bytes', async (t) => {
  const mainModule = loadMainModule(t);
  const embedded = createEmbeddedRuntimeFixture(t);
  fs.writeFileSync(path.join(embedded.rootDir, 'llama-server'), 'corrupt helper bytes');
  const records = [];

  const resolved = await mainModule.resolveLocalModelBinary({
    embeddedRoot: embedded.rootDir,
    platform: 'darwin',
    arch: 'arm64',
    spawnImpl: makeRuntimeAvailabilitySpawn(records, () => 'error'),
    logImpl: () => undefined,
  });

  assert.equal(resolved, null);
  assert.deepEqual(records.map((record) => record.command), ['ollama']);
});

test('local model binary resolution rejects missing or corrupt embedded dependency files', async (t) => {
  const mainModule = loadMainModule(t);
  const missing = createEmbeddedRuntimeFixture(t);
  fs.rmSync(path.join(missing.rootDir, missing.dependencyPath));
  const missingRecords = [];
  assert.equal(await mainModule.resolveLocalModelBinary({
    embeddedRoot: missing.rootDir,
    platform: 'darwin',
    arch: 'arm64',
    spawnImpl: makeRuntimeAvailabilitySpawn(missingRecords, () => 'error'),
    logImpl: () => undefined,
  }), null);
  assert.deepEqual(missingRecords.map((record) => record.command), ['ollama']);

  const corrupt = createEmbeddedRuntimeFixture(t);
  fs.writeFileSync(path.join(corrupt.rootDir, corrupt.dependencyPath), 'corrupt library bytes');
  const corruptRecords = [];
  assert.equal(await mainModule.resolveLocalModelBinary({
    embeddedRoot: corrupt.rootDir,
    platform: 'darwin',
    arch: 'arm64',
    spawnImpl: makeRuntimeAvailabilitySpawn(corruptRecords, () => 'error'),
    logImpl: () => undefined,
  }), null);
  assert.deepEqual(corruptRecords.map((record) => record.command), ['ollama']);
});

test('embedded runtime validation supports the packaged Windows layout', (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });
  const embedded = createEmbeddedRuntimeFixture(t, { platform: 'win32', arch: 'x64' });

  assert.deepEqual(
    mainModule.resolveEmbeddedLocalModelRuntime({
      rootDir: embedded.rootDir,
      platform: 'win32',
      arch: 'x64',
    }),
    {
      command: embedded.command,
      rootDir: embedded.rootDir,
      source: mainModule.DESKTOP_LOCAL_MODEL_RUNTIME_SOURCE.EMBEDDED,
      version: 'v0.32.3',
    }
  );
});

test('detection reports running with installed models when the runtime answers', async (t) => {
  const mainModule = loadMainModule(t);
  mainModule.__setLocalModelStateForTest(null);
  const requestImpl = makeStagedJsonRequest([
    { statusCode: 200, jsonBody: { models: [{ name: 'qwen3:8b' }] } },
  ]);

  const detection = await mainModule.detectLocalModelRuntime({
    baseUrl: 'http://127.0.0.1:11434',
    requestImpl,
    spawnImpl: () => {
      throw new Error('spawn must not run when the runtime already answers');
    },
  });

  assert.equal(detection.status, mainModule.DESKTOP_LOCAL_MODEL_STATUS.RUNNING);
  assert.deepEqual(detection.installedModels, ['qwen3:8b']);
});

test('detection distinguishes stopped runtime from a missing install', async (t) => {
  const mainModule = loadMainModule(t);

  const stoppedRecords = [];
  const stopped = await mainModule.detectLocalModelRuntime({
    baseUrl: 'http://127.0.0.1:11434',
    requestImpl: makeStagedJsonRequest([{ connectionError: true }]),
    spawnImpl: makeLocalModelSpawn(stoppedRecords),
  });
  assert.equal(stopped.status, mainModule.DESKTOP_LOCAL_MODEL_STATUS.STOPPED);
  assert.equal(stopped.installed, true);
  assert.deepEqual(stoppedRecords[0].args, ['--version']);

  const missing = await mainModule.detectLocalModelRuntime({
    baseUrl: 'http://127.0.0.1:11434',
    requestImpl: makeStagedJsonRequest([{ connectionError: true }]),
    spawnImpl: (command, args) => {
      const child = new EventEmitter();
      child.kill = () => undefined;
      setImmediate(() => child.emit('error', new Error('ENOENT')));
      return child;
    },
  });
  assert.equal(missing.status, mainModule.DESKTOP_LOCAL_MODEL_STATUS.NOT_INSTALLED);
  assert.equal(missing.installed, false);
});

test('starting the runtime spawns a whitelisted daemon with array arguments only', async (t) => {
  const mainModule = loadMainModule(t);
  mainModule.__setLocalModelStateForTest(null);
  const records = [];
  const requestImpl = makeStagedJsonRequest([
    { connectionError: true },
    { statusCode: 200, jsonBody: { models: [{ name: 'qwen3:8b' }] } },
  ]);

  const state = await mainModule.startManagedLocalModelRuntime({
    requestImpl,
    spawnImpl: makeLocalModelSpawn(records),
    startTimeoutMs: 3000,
    sourceEnv: {
      PATH: '/custom/bin',
      OLLAMA_HOST: '127.0.0.1:22345',
      OLLAMA_MODELS: '/existing/system-models',
    },
  });

  const serveCall = records.find((call) => Array.isArray(call.args) && call.args.includes('serve'));
  assert.ok(serveCall, 'expected a serve spawn');
  assert.equal(serveCall.command, 'ollama');
  assert.deepEqual(serveCall.args, ['serve']);
  assert.notEqual(serveCall.options.shell, true);
  assert.equal(serveCall.options.env.OLLAMA_HOST, '127.0.0.1:22345');
  assert.equal(serveCall.options.env.OLLAMA_MODELS, '/existing/system-models');
  assert.equal(state.status, mainModule.DESKTOP_LOCAL_MODEL_STATUS.RUNNING);
  assert.equal(state.managed, true);
  assert.equal(state.runtimeSource, mainModule.DESKTOP_LOCAL_MODEL_RUNTIME_SOURCE.SYSTEM);

  mainModule.__setLocalModelServeProcessForTest(null);
});

test('starting reuses an already healthy Ollama endpoint without spawning', async (t) => {
  const mainModule = loadMainModule(t);
  mainModule.__setLocalModelStateForTest(null);

  const state = await mainModule.startManagedLocalModelRuntime({
    baseUrl: 'http://127.0.0.1:11434',
    requestImpl: makeStagedJsonRequest([
      { statusCode: 200, jsonBody: { models: [{ name: 'qwen3:8b' }] } },
    ]),
    spawnImpl: () => {
      throw new Error('spawn must not run for a healthy endpoint');
    },
  });

  assert.equal(state.status, mainModule.DESKTOP_LOCAL_MODEL_STATUS.RUNNING);
  assert.equal(state.managed, false);
  assert.equal(
    state.runtimeSource,
    mainModule.DESKTOP_LOCAL_MODEL_RUNTIME_SOURCE.EXTERNAL_SERVICE
  );
});

test('starting the embedded runtime isolates its host, models, and working directory', async (t) => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-embedded-model-data-'));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  const mainModule = loadMainModule(t);
  const embedded = createEmbeddedRuntimeFixture(t);
  const records = [];
  mainModule.__setLocalModelStateForTest(null);

  const spawnImpl = makeRuntimeAvailabilitySpawn(records, (command, args) => {
    if (command === 'ollama') {
      return 'error';
    }
    if (args.includes('--version')) {
      return 0;
    }
    return null;
  });
  const state = await mainModule.startManagedLocalModelRuntime({
    baseUrl: 'http://127.0.0.1:11434',
    requestImpl: makeStagedJsonRequest([
      { connectionError: true },
      { statusCode: 200, jsonBody: { models: [] } },
    ]),
    spawnImpl,
    embeddedRoot: embedded.rootDir,
    platform: 'darwin',
    arch: 'arm64',
    sourceEnv: {
      PATH: '/custom/bin',
      OLLAMA_HOST: '127.0.0.1:22345',
      OLLAMA_MODELS: '/ambient/models',
    },
    appDir: tmpDir,
    startTimeoutMs: 3000,
  });

  const serveCall = records.find((call) => call.args.includes('serve'));
  assert.ok(serveCall);
  assert.equal(serveCall.command, embedded.command);
  assert.equal(serveCall.options.cwd, embedded.rootDir);
  assert.equal(serveCall.options.env.OLLAMA_HOST, '127.0.0.1:11434');
  assert.equal(
    serveCall.options.env.OLLAMA_MODELS,
    path.join(tmpDir, 'data', 'ollama', 'models')
  );
  assert.equal(state.runtimeSource, mainModule.DESKTOP_LOCAL_MODEL_RUNTIME_SOURCE.EMBEDDED);
  assert.equal(Object.hasOwn(state, 'runtimeBinary'), false);

  mainModule.__setLocalModelServeProcessForTest(null);
});

test('starting a missing runtime degrades gracefully without throwing', async (t) => {
  const mainModule = loadMainModule(t);
  mainModule.__setLocalModelStateForTest(null);

  const state = await mainModule.startManagedLocalModelRuntime({
    requestImpl: makeStagedJsonRequest([{ connectionError: true }]),
    spawnImpl: (command, args) => {
      const child = new EventEmitter();
      child.kill = () => undefined;
      setImmediate(() => child.emit('error', new Error('ENOENT')));
      return child;
    },
    startTimeoutMs: 1000,
  });

  assert.equal(state.status, mainModule.DESKTOP_LOCAL_MODEL_STATUS.NOT_INSTALLED);
  assert.match(state.message, /not installed/i);
});

test('stopping the runtime only terminates the desktop-managed process', async (t) => {
  const mainModule = loadMainModule(t);
  mainModule.__setLocalModelStateForTest(null);
  const managed = new EventEmitter();
  managed.pid = 9191;
  managed.exitCode = null;
  managed.signalCode = null;
  let killed = false;
  managed.kill = () => {
    killed = true;
    managed.exitCode = 0;
    return true;
  };
  mainModule.__setLocalModelServeProcessForTest(managed);

  const state = await mainModule.stopManagedLocalModelRuntime();
  assert.equal(killed, true);
  assert.equal(state.status, mainModule.DESKTOP_LOCAL_MODEL_STATUS.STOPPED);
  assert.equal(mainModule.__getLocalModelServeProcessForTest(), null);
});

test('Windows runtime stop waits for taskkill before clearing managed state', async (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });
  mainModule.__setLocalModelStateForTest(null);
  const managed = new EventEmitter();
  managed.pid = 9292;
  managed.exitCode = null;
  managed.signalCode = null;
  const terminator = new EventEmitter();
  const spawnCalls = [];
  mainModule.__setLocalModelServeProcessForTest(managed);

  let settled = false;
  const pending = mainModule.stopManagedLocalModelRuntime({
    platform: 'win32',
    timeoutMs: 1000,
    spawnImpl: (command, args, options) => {
      spawnCalls.push({ command, args, options });
      return terminator;
    },
  }).then((state) => {
    settled = true;
    return state;
  });

  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(settled, false);
  assert.equal(mainModule.__getLocalModelServeProcessForTest(), managed);
  assert.deepEqual(spawnCalls, [{
    command: 'taskkill',
    args: ['/PID', '9292', '/T', '/F'],
    options: { windowsHide: true, stdio: 'ignore' },
  }]);

  managed.exitCode = 0;
  managed.emit('exit', 0);
  const state = await pending;
  assert.equal(state.status, mainModule.DESKTOP_LOCAL_MODEL_STATUS.STOPPED);
  assert.equal(mainModule.__getLocalModelServeProcessForTest(), null);
});

test('Windows runtime stop fails closed when taskkill cannot terminate the process', async (t) => {
  const mainModule = loadMainModule(t, { platform: 'win32' });
  const managed = new EventEmitter();
  managed.pid = 9393;
  managed.exitCode = null;
  managed.signalCode = null;
  mainModule.__setLocalModelServeProcessForTest(managed);

  const pending = mainModule.stopManagedLocalModelRuntime({
    platform: 'win32',
    timeoutMs: 20,
    spawnImpl: () => new EventEmitter(),
  });

  await assert.rejects(pending, /Ollama did not stop within 20ms/);
  assert.equal(mainModule.__getLocalModelServeProcessForTest(), managed);
});

test('pull refuses names outside the curated allowlist before any network call', async (t) => {
  const mainModule = loadMainModule(t);
  mainModule.__setLocalModelStateForTest(null);
  const requestImpl = makeStagedJsonRequest([{ statusCode: 200, jsonBody: {} }]);

  const injection = await mainModule.pullLocalModel('qwen3:8b; rm -rf /', { requestImpl });
  assert.equal(injection.ok, false);
  assert.equal(injection.error, 'model-not-allowed');

  const unlisted = await mainModule.pullLocalModel('mistral:latest', { requestImpl });
  assert.equal(unlisted.ok, false);
  assert.equal(unlisted.error, 'model-not-allowed');

  assert.equal(requestImpl.calls.length, 0);
});

test('pull streams a curated model and reports progress', async (t) => {
  const mainModule = loadMainModule(t);
  mainModule.__setLocalModelStateForTest(null);
  const requestImpl = makeStagedJsonRequest([
    { statusCode: 200, ndjson: [
      { status: 'pulling manifest' },
      { status: 'downloading', total: 100, completed: 50 },
      { status: 'success', total: 100, completed: 100 },
    ] },
    { statusCode: 200, jsonBody: { models: [{ name: 'qwen3:8b' }] } },
  ]);

  const result = await mainModule.pullLocalModel('qwen3:8b', { requestImpl });
  assert.equal(result.ok, true);
  assert.equal(result.modelId, 'qwen3:8b');
});

test('pull does not activate when Ollama closes without terminal success', async (t) => {
  const mainModule = loadMainModule(t);
  mainModule.__setLocalModelStateForTest(null);
  const requestImpl = makeStagedJsonRequest([
    { statusCode: 200, ndjson: [
      { status: 'pulling manifest' },
      { status: 'downloading', total: 100, completed: 100 },
    ] },
    { statusCode: 200, jsonBody: { models: [] } },
  ]);

  const result = await mainModule.pullLocalModel('qwen3:8b', { requestImpl });

  assert.equal(result.ok, false);
  assert.equal(result.error, 'pull-failed');
});

test('desktop rejects oversized local model JSON and progress events', async (t) => {
  const mainModule = loadMainModule(t);
  const oversizedJson = makeStagedJsonRequest([{
    statusCode: 200,
    jsonBody: { value: 'x'.repeat(mainModule.DESKTOP_LOCAL_MODEL_MAX_JSON_BYTES) },
  }]);
  await assert.rejects(
    mainModule.requestLocalModelJson({
      baseUrl: 'http://127.0.0.1:11434',
      pathname: '/api/tags',
      requestImpl: oversizedJson,
    }),
    /too large/i,
  );

  const oversizedProgress = makeStagedJsonRequest([{
    statusCode: 200,
    ndjson: [{ status: 'x'.repeat(mainModule.DESKTOP_LOCAL_MODEL_MAX_EVENT_BYTES) }],
  }]);
  await assert.rejects(
    mainModule.requestLocalModelPullStream({
      baseUrl: 'http://127.0.0.1:11434',
      modelId: 'qwen3:8b',
      requestImpl: oversizedProgress,
    }),
    /too large/i,
  );

  const oversizedWhitespace = makeStagedJsonRequest([{
    statusCode: 200,
    rawChunks: [`${' '.repeat(mainModule.DESKTOP_LOCAL_MODEL_MAX_EVENT_BYTES)}{}\n`],
  }]);
  await assert.rejects(
    mainModule.requestLocalModelPullStream({
      baseUrl: 'http://127.0.0.1:11434',
      modelId: 'qwen3:8b',
      requestImpl: oversizedWhitespace,
    }),
    /too large/i,
  );
  assert.equal(oversizedWhitespace.calls[0].responseDestroyed, true);
});

test('desktop Stop is serialized behind an active local model operation', async (t) => {
  const mainModule = loadMainModule(t);
  const webContents = {
    isDestroyed: () => false,
    send: () => undefined,
  };
  mainModule.__setMainWindowForTest({
    isDestroyed: () => false,
    webContents,
  });
  let killed = false;
  mainModule.__setLocalModelServeProcessForTest({
    pid: 9191,
    exitCode: null,
    signalCode: null,
    kill: () => {
      killed = true;
      return true;
    },
  });
  let releaseOperation;
  const inFlight = mainModule.runLocalModelOperation(() => new Promise((resolve) => {
    releaseOperation = resolve;
  }));

  const stopHandler = mainModule.__getIpcMainHandler(
    mainModule.DESKTOP_LOCAL_MODEL_STOP_CHANNEL,
  );
  const result = await stopHandler({ sender: webContents });

  assert.equal(result.error, 'busy');
  assert.equal(killed, false);
  releaseOperation({ ok: true });
  await inFlight;
});

test('desktop deletion rejects non-catalog names before network activity', async (t) => {
  const mainModule = loadMainModule(t);
  const requestImpl = makeStagedJsonRequest([{ statusCode: 200, jsonBody: {} }]);

  const result = await mainModule.removeLocalModel('mistral:latest', { requestImpl });

  assert.equal(result.ok, false);
  assert.equal(result.error, 'model-not-allowed');
  assert.equal(requestImpl.calls.length, 0);
});

test('desktop deletion sends the Ollama DELETE request body', async (t) => {
  const mainModule = loadMainModule(t);
  mainModule.__setLocalModelStateForTest(null);
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-localmodel-delete-'));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  const envFile = path.join(tmpDir, '.env');
  fs.writeFileSync(envFile, 'LLM_OLLAMA_MODELS=qwen3:8b\n');
  const requestImpl = makeStagedJsonRequest([
    { statusCode: 200, jsonBody: {} },
    { statusCode: 200, jsonBody: { models: [] } },
  ]);

  const result = await mainModule.removeLocalModel('qwen3:8b', { requestImpl, envFile });

  assert.deepEqual(result, { ok: true, modelId: 'qwen3:8b' });
  assert.equal(requestImpl.calls[0].target.pathname, '/api/delete');
  assert.equal(requestImpl.calls[0].options.method, 'DELETE');
  assert.deepEqual(
    JSON.parse(Buffer.concat(requestImpl.calls[0].body).toString('utf-8')),
    { name: 'qwen3:8b' }
  );
});

test('desktop deletion rejects every active assignment before network activity', async (t) => {
  const mainModule = loadMainModule(t);
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-localmodel-active-'));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  const envFile = path.join(tmpDir, '.env');
  const requestImpl = makeStagedJsonRequest([{ statusCode: 200, jsonBody: {} }]);

  fs.writeFileSync(envFile, 'LITELLM_MODEL=ollama/qwen3:8b\n');
  const primaryResult = await mainModule.removeLocalModel('qwen3:8b', { requestImpl, envFile });
  assert.equal(primaryResult.error, 'model-in-use');

  fs.writeFileSync(
    envFile,
    'AGENT_LITELLM_MODEL=modelref:v1:local_ollama:ollama%2Fqwen3%3A8b\n'
  );
  const agentResult = await mainModule.removeLocalModel('qwen3:8b', { requestImpl, envFile });
  assert.equal(agentResult.error, 'model-in-use');

  fs.writeFileSync(envFile, 'VISION_MODEL=ollama/qwen3:8b\n');
  const visionResult = await mainModule.removeLocalModel('qwen3:8b', { requestImpl, envFile });
  assert.equal(visionResult.error, 'model-in-use');

  fs.writeFileSync(envFile, 'LITELLM_FALLBACK_MODELS=ollama/qwen3:8b\n');
  const fallbackResult = await mainModule.removeLocalModel('qwen3:8b', { requestImpl, envFile });
  assert.equal(fallbackResult.error, 'model-in-use');

  fs.writeFileSync(
    envFile,
    'VISION_MODEL=modelref:v1:local_ollama:ollama%2Fqwen3%3A8b\n'
  );
  const visionRefResult = await mainModule.removeLocalModel('qwen3:8b', { requestImpl, envFile });
  assert.equal(visionRefResult.error, 'model-in-use');

  fs.writeFileSync(
    envFile,
    'LITELLM_FALLBACK_MODELS=openai/gpt-5,modelref:v1:local_ollama:ollama%2Fqwen3%3A8b\n'
  );
  const fallbackRefResult = await mainModule.removeLocalModel('qwen3:8b', { requestImpl, envFile });
  assert.equal(fallbackRefResult.error, 'model-in-use');

  fs.writeFileSync(
    envFile,
    [
      'LLM_CONFIG_MODE=channels',
      'LLM_CHANNELS=ollama',
      'LLM_OLLAMA_MODELS=qwen3:8b',
      'LLM_OLLAMA_ENABLED=true',
      '',
    ].join('\n')
  );
  const implicitResult = await mainModule.removeLocalModel('qwen3:8b', { requestImpl, envFile });
  assert.equal(implicitResult.error, 'model-in-use');
  assert.equal(requestImpl.calls.length, 0);
});

test('desktop deletion ignores an implicit channel model when YAML wins auto mode', async (t) => {
  const mainModule = loadMainModule(t);
  mainModule.__setLocalModelStateForTest(null);
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-localmodel-yaml-'));
  t.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
  const envFile = path.join(tmpDir, '.env');
  fs.writeFileSync(
    envFile,
    [
      'LLM_CONFIG_MODE=auto',
      'LITELLM_CONFIG=/tmp/litellm.yaml',
      'LLM_CHANNELS=ollama',
      'LLM_OLLAMA_MODELS=qwen3:8b',
      'LLM_OLLAMA_ENABLED=true',
      '',
    ].join('\n')
  );
  const requestImpl = makeStagedJsonRequest([
    { statusCode: 200, jsonBody: {} },
    { statusCode: 200, jsonBody: { models: [] } },
  ]);

  const result = await mainModule.removeLocalModel('qwen3:8b', { requestImpl, envFile });

  assert.deepEqual(result, { ok: true, modelId: 'qwen3:8b' });
  assert.equal(requestImpl.calls[0].target.pathname, '/api/delete');
});

test('local model IPC rejects foreign renderers and serves the main Web window', async (t) => {
  const mainModule = loadMainModule(t);
  mainModule.__setLocalModelStateForTest(null);

  const detectHandler = mainModule.__getIpcMainHandler('desktop-local-model:detect');
  await assert.rejects(
    async () => detectHandler({ sender: { id: 'other' } }),
    /Unauthorized local model IPC sender/
  );

  const stateEvents = [];
  const mainWebContents = {
    send: (channel, payload) => stateEvents.push({ channel, payload }),
    isDestroyed: () => false,
  };
  const mainWindow = {
    isDestroyed: () => false,
    webContents: mainWebContents,
  };
  mainModule.__setMainWindowForTest(mainWindow);
  t.after(() => mainModule.__setMainWindowForTest(null));

  const stateHandler = mainModule.__getIpcMainHandler('desktop-local-model:get-state');
  const state = stateHandler({ sender: mainWebContents });
  assert.equal(typeof state.status, 'string');
  assert.ok(state.totalMemoryGb > 0);

  mainModule.stopManagedLocalModelRuntime();
  assert.equal(stateEvents.at(-1).channel, mainModule.DESKTOP_LOCAL_MODEL_STATE_EVENT);
  assert.equal(stateEvents.at(-1).payload.status, 'stopped');
});

test('desktop package retires the standalone model surface and keeps embedded runtime assets', () => {
  const packageMetadata = JSON.parse(
    fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf-8')
  );

  assert.equal(packageMetadata.build.files.includes('model-preload.js'), false);
  assert.equal(fs.existsSync(path.join(__dirname, '..', 'model-preload.js')), false);
  assert.equal(fs.existsSync(path.join(__dirname, '..', 'renderer', 'local-models.html')), false);
  assert.equal(fs.existsSync(path.join(__dirname, '..', 'renderer', 'local-models.js')), false);
  assert.equal(
    packageMetadata.scripts['prepare:ollama'],
    'node ../../scripts/prepare-embedded-ollama.js'
  );
  assert.equal(packageMetadata.scripts.prebuild, 'npm run prepare:ollama');
  assert.equal(packageMetadata.scripts['build:electron'], 'electron-builder');
  assert.ok(packageMetadata.build.extraResources.some((entry) =>
    entry.from === 'vendor/ollama' && entry.to === 'ollama'));
  assert.ok(packageMetadata.build.extraResources.some((entry) =>
    entry.from === '../../THIRD_PARTY_NOTICES' && entry.to === 'THIRD_PARTY_NOTICES'));
});

test('starting never leaves more than one managed daemon alive', async (t) => {
  const mainModule = loadMainModule(t);
  mainModule.__setLocalModelStateForTest(null);

  const priorProcess = new EventEmitter();
  priorProcess.pid = 5150;
  priorProcess.exitCode = null;
  priorProcess.signalCode = null;
  let priorKilled = false;
  priorProcess.kill = () => {
    priorKilled = true;
    priorProcess.exitCode = 0;
    return true;
  };
  mainModule.__setLocalModelServeProcessForTest(priorProcess);

  const records = [];
  const requestImpl = makeStagedJsonRequest([
    { connectionError: true },
    { statusCode: 200, jsonBody: { models: [] } },
  ]);

  const state = await mainModule.startManagedLocalModelRuntime({
    requestImpl,
    spawnImpl: makeLocalModelSpawn(records),
    startTimeoutMs: 3000,
  });

  assert.equal(priorKilled, true);
  assert.equal(state.status, mainModule.DESKTOP_LOCAL_MODEL_STATUS.RUNNING);
  const tracked = mainModule.__getLocalModelServeProcessForTest();
  assert.notEqual(tracked, priorProcess);

  mainModule.__setLocalModelServeProcessForTest(null);
});
