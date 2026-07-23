const {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
  nativeImage,
  nativeTheme,
  shell,
  Tray,
} = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const net = require('net');
const http = require('http');
const https = require('https');
const { TextDecoder } = require('util');

let mainWindow = null;
let assistantWindow = null;
let assistantWindowLoadPromise = null;
let desktopTray = null;
let desktopIsQuitting = false;
let desktopAssistantLastReadyAt = '';
let backendProcess = null;
let logFilePath = null;
let backendStartError = null;
let desktopUpdateState = null;
let lastNotifiedUpdateVersion = '';
let lastPromptedInstallVersion = '';
let electronAutoUpdater = undefined;
let electronAutoUpdaterConfigured = false;
let electronUpdateCheckInFlight = false;
let desktopMainPageUrl = '';
let desktopWebReady = false;
let pendingDesktopDeepLinkRoute = null;
let pendingDesktopDeepLinkOutcome = null;
let desktopDeepLinkNavigationInFlight = false;
let desktopDeepLinkFlushPromise = null;
let localModelWindow = null;
let localModelWindowLoadPromise = null;
let localModelServeProcess = null;
let localModelState = null;
let localModelOperationInFlight = false;

function resolveWindowBackgroundColor() {
  return nativeTheme.shouldUseDarkColors ? '#08080c' : '#f4f7fb';
}

const isWindows = process.platform === 'win32';
const isMac = process.platform === 'darwin';
const appRootDev = path.resolve(__dirname, '..', '..');
const GITHUB_OWNER = 'SiinXu';
const GITHUB_REPO = 'stock-pulse-ai';
const RELEASES_PAGE_URL = `https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/releases`;
const LATEST_RELEASE_API_URL = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/releases/latest`;
const DEFAULT_REQUEST_TIMEOUT_MS = 5000;
const DESKTOP_UPDATE_BACKUP_DIR = '.dsa-desktop-update-backup';
const DESKTOP_UPDATE_BACKUP_MANIFEST_FILE = 'runtime-state.json';
const DESKTOP_BRAND_MIGRATION_RECORD_FILE = '.stockpulse-brand-migration.json';
const DESKTOP_BRAND_MIGRATION_TEMP_SUFFIX = '.stockpulse-migration.tmp';
const PROVIDER_DAILY_CACHE_DIR_ENV_KEY = 'PROVIDER_DAILY_CACHE_DIR';
const DESKTOP_PROVIDER_DAILY_CACHE_RELATIVE_PATH = path.join('data', 'provider_cache', 'daily');
const LEGACY_DESKTOP_PRODUCT_NAMES = Object.freeze(['Daily Stock Analysis']);
const WINDOWS_NSIS_UNINSTALLER_NAMES = Object.freeze([
  'Uninstall StockPulse.exe',
  'Uninstall Daily Stock Analysis.exe',
]);
const DESKTOP_BACKEND_DEFAULT_HOST = '127.0.0.1';
const DESKTOP_PROTOCOL = 'stockpulse';
const DESKTOP_PROTOCOL_HOST = 'app';
const DESKTOP_DEEP_LINK_MAX_LENGTH = 4096;
const DESKTOP_ASSISTANT_GET_STATE_CHANNEL = 'desktop-assistant:get-state';
const DESKTOP_ASSISTANT_OPEN_ACTION_CHANNEL = 'desktop-assistant:open-action';
const DESKTOP_ASSISTANT_SET_MAIN_VISIBILITY_CHANNEL = 'desktop-assistant:set-main-visibility';
const DESKTOP_ASSISTANT_HIDE_CHANNEL = 'desktop-assistant:hide';
const DESKTOP_ASSISTANT_STATE_EVENT = 'desktop-assistant:state';
const DESKTOP_ASSISTANT_WINDOW_WIDTH = 368;
const DESKTOP_ASSISTANT_WINDOW_HEIGHT = 484;
const DESKTOP_ASSISTANT_STOCK_CODE_PATTERN = /^[A-Za-z0-9.]{1,16}$/;
const DESKTOP_ASSISTANT_ACTION_ROUTES = Object.freeze({
  analysis: '/',
  alerts: '/alerts',
  portfolio: '/portfolio',
  screening: '/screening',
});
const DESKTOP_DEEP_LINK_EXACT_PATHS = Object.freeze(new Set([
  '/',
  '/alerts',
  '/backtest',
  '/chat',
  '/decision-signals',
  '/portfolio',
  '/screening',
  '/settings',
  '/usage',
]));
const DESKTOP_DEEP_LINK_STOCK_PATH_PATTERN = /^\/stocks\/[A-Za-z0-9.]{1,16}$/;
// Local model lifecycle (issue #203): the desktop shell manages an Ollama
// runtime and its models without ever building a shell command line. The
// binary name is a fixed allowlist entry and the only spawn arguments are the
// hardcoded `--version` probe and `serve`; user-influenced values (model
// names) travel exclusively over loopback HTTP request bodies.
const DESKTOP_LOCAL_MODEL_RUNTIME = 'ollama';
const DESKTOP_LOCAL_MODEL_BINARY = 'ollama';
const DESKTOP_LOCAL_MODEL_DEFAULT_BASE_URL = 'http://127.0.0.1:11434';
const DESKTOP_LOCAL_MODEL_BASE_URL_ENV_KEY = 'LLM_OLLAMA_BASE_URL';
const DESKTOP_LOCAL_MODEL_REQUEST_TIMEOUT_MS = 4000;
const DESKTOP_LOCAL_MODEL_DETECT_TIMEOUT_MS = 4000;
const DESKTOP_LOCAL_MODEL_START_TIMEOUT_MS = 20000;
const DESKTOP_LOCAL_MODEL_PULL_TIMEOUT_MS = 30 * 60 * 1000;
const DESKTOP_LOCAL_MODEL_NAME_PATTERN =
  /^[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[a-z0-9]+(?:[._-][a-z0-9]+)*)?$/i;
const DESKTOP_LOCAL_MODEL_MAX_NAME_LENGTH = 96;
const DESKTOP_LOCAL_MODEL_INSTALL_GUIDE_URL = 'https://ollama.com/download';
// Curated recommended presets with hardware guidance. Only these ids may be
// pulled from the desktop UI; arbitrary user-typed names are never downloaded.
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
const DESKTOP_LOCAL_MODEL_PRESET_IDS = Object.freeze(
  new Set(DESKTOP_LOCAL_MODEL_PRESETS.map((preset) => preset.id))
);
const DESKTOP_LOCAL_MODEL_STATUS = Object.freeze({
  UNKNOWN: 'unknown',
  NOT_INSTALLED: 'not-installed',
  STOPPED: 'stopped',
  STARTING: 'starting',
  RUNNING: 'running',
  ERROR: 'error',
});
const DESKTOP_LOCAL_MODEL_GET_STATE_CHANNEL = 'desktop-local-model:get-state';
const DESKTOP_LOCAL_MODEL_DETECT_CHANNEL = 'desktop-local-model:detect';
const DESKTOP_LOCAL_MODEL_START_CHANNEL = 'desktop-local-model:start';
const DESKTOP_LOCAL_MODEL_STOP_CHANNEL = 'desktop-local-model:stop';
const DESKTOP_LOCAL_MODEL_PULL_CHANNEL = 'desktop-local-model:pull';
const DESKTOP_LOCAL_MODEL_REGISTER_CHANNEL = 'desktop-local-model:register';
const DESKTOP_LOCAL_MODEL_OPEN_GUIDE_CHANNEL = 'desktop-local-model:open-guide';
const DESKTOP_LOCAL_MODEL_STATE_EVENT = 'desktop-local-model:state';
const DESKTOP_LOCAL_MODEL_WINDOW_WIDTH = 520;
const DESKTOP_LOCAL_MODEL_WINDOW_HEIGHT = 640;
const PUBLIC_BIND_HOSTS = Object.freeze(new Set(['0.0.0.0', '::', '[::]', '*']));
const MAC_DESKTOP_CLI_PATH_ENTRIES = Object.freeze([
  '/opt/homebrew/bin',
  '/usr/local/bin',
  '/opt/homebrew/sbin',
  '/usr/local/sbin',
]);
const MAC_DESKTOP_SYSTEM_PATH_ENTRIES = Object.freeze([
  '/usr/bin',
  '/bin',
  '/usr/sbin',
  '/sbin',
]);
const DESKTOP_BACKEND_PATH_DELIMITER = isWindows ? ';' : ':';
const DESKTOP_UPDATE_RUNTIME_RELATIVE_FILES = Object.freeze([
  '.env',
  path.join('data', 'stock_analysis.db'),
  path.join('data', 'stock_analysis.db-wal'),
  path.join('data', 'stock_analysis.db-shm'),
  DESKTOP_PROVIDER_DAILY_CACHE_RELATIVE_PATH,
  path.join('data', 'alphasift', 'hotspots.json'),
  path.join('data', 'alphasift', 'hotspot.history.jsonl'),
  path.join('data', 'alphasift', 'hotspot_details'),
  path.join('data', 'alphasift', 'snapshot.last_good.json'),
  path.join('logs', 'desktop.log'),
]);
const LEGACY_USER_DATA_RELATIVE_PATHS = Object.freeze([
  '.env',
  'data',
  'logs',
  DESKTOP_UPDATE_BACKUP_DIR,
  'Local Storage',
  'Session Storage',
  'IndexedDB',
  path.join('Network', 'Cookies'),
  path.join('Network', 'Cookies-journal'),
  'Preferences',
  'Local State',
]);

const UPDATE_STATUS = Object.freeze({
  IDLE: 'idle',
  CHECKING: 'checking',
  UP_TO_DATE: 'up-to-date',
  UPDATE_AVAILABLE: 'update-available',
  DOWNLOADING: 'downloading',
  UPDATE_DOWNLOADED: 'update-downloaded',
  INSTALLING: 'installing',
  ERROR: 'error',
});

const UPDATE_MODE = Object.freeze({
  AUTO: 'auto',
  MANUAL: 'manual',
});

function isAllowedDesktopDeepLinkPath(pathname) {
  return DESKTOP_DEEP_LINK_EXACT_PATHS.has(pathname)
    || DESKTOP_DEEP_LINK_STOCK_PATH_PATTERN.test(pathname);
}

function parseDesktopDeepLink(rawUrl) {
  if (typeof rawUrl !== 'string'
    || rawUrl.length === 0
    || rawUrl.length > DESKTOP_DEEP_LINK_MAX_LENGTH
    || rawUrl.trim() !== rawUrl
    || /[\u0000-\u0020\u007F]/.test(rawUrl)) {
    return null;
  }

  const schemeSeparator = rawUrl.indexOf('://');
  if (schemeSeparator <= 0
    || rawUrl.slice(0, schemeSeparator).toLowerCase() !== DESKTOP_PROTOCOL) {
    return null;
  }

  const authorityStart = schemeSeparator + 3;
  const authorityRemainder = rawUrl.slice(authorityStart);
  const authorityEndOffset = authorityRemainder.search(/[/?#]/);
  if (authorityEndOffset < 0) {
    return null;
  }
  const authorityEnd = authorityStart + authorityEndOffset;
  const rawAuthority = rawUrl.slice(authorityStart, authorityEnd);
  if (rawAuthority.toLowerCase() !== DESKTOP_PROTOCOL_HOST || rawUrl[authorityEnd] !== '/') {
    return null;
  }

  const searchIndex = rawUrl.indexOf('?', authorityEnd);
  const hashIndex = rawUrl.indexOf('#', authorityEnd);
  const pathEndCandidates = [searchIndex, hashIndex].filter((index) => index >= 0);
  const pathEnd = pathEndCandidates.length ? Math.min(...pathEndCandidates) : rawUrl.length;
  const rawPath = rawUrl.slice(authorityEnd, pathEnd);

  let url;
  try {
    url = new URL(rawUrl);
  } catch (_error) {
    return null;
  }

  if (url.protocol !== `${DESKTOP_PROTOCOL}:`
    || url.hostname.toLowerCase() !== DESKTOP_PROTOCOL_HOST
    || url.host.toLowerCase() !== DESKTOP_PROTOCOL_HOST
    || url.username
    || url.password
    || url.port
    || url.hash
    || url.pathname !== rawPath
    || url.search.length > DESKTOP_DEEP_LINK_MAX_LENGTH
    || !isAllowedDesktopDeepLinkPath(url.pathname)) {
    return null;
  }

  return `${url.pathname}${url.search}`;
}

function extractDesktopDeepLink(argv = []) {
  if (!Array.isArray(argv)) {
    return null;
  }
  return argv.find(
    (value) => typeof value === 'string' && value.toLowerCase().startsWith(`${DESKTOP_PROTOCOL}:`)
  ) || null;
}

function buildDesktopDeepLinkTargetUrl(mainPageUrl, route) {
  const baseUrl = new URL(mainPageUrl);
  if (!['http:', 'https:'].includes(baseUrl.protocol)) {
    throw new TypeError('Desktop Web origin must use HTTP or HTTPS');
  }

  const targetUrl = new URL(route, `${baseUrl.origin}/`);
  if (targetUrl.origin !== baseUrl.origin) {
    throw new TypeError('Desktop deep link must remain on the private Web origin');
  }

  for (const key of ['desktop_version', 'cache_bust']) {
    if (baseUrl.searchParams.has(key)) {
      targetUrl.searchParams.set(key, baseUrl.searchParams.get(key));
    }
  }
  return targetUrl.toString();
}

function sanitizeUrlForLog(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return `${url.protocol}//${url.host}${url.pathname}`;
  } catch (_error) {
    return '[invalid URL]';
  }
}

function normalizeDesktopAssistantStockCode(rawStockCode) {
  if (typeof rawStockCode !== 'string') {
    return null;
  }
  const stockCode = rawStockCode.trim().toUpperCase();
  return DESKTOP_ASSISTANT_STOCK_CODE_PATTERN.test(stockCode) ? stockCode : null;
}

function buildDesktopAssistantRoute(action, rawStockCode = '') {
  if (action === 'stock') {
    const stockCode = normalizeDesktopAssistantStockCode(rawStockCode);
    return stockCode ? `/stocks/${stockCode}` : null;
  }

  if (!Object.prototype.hasOwnProperty.call(DESKTOP_ASSISTANT_ACTION_ROUTES, action)) {
    return null;
  }
  return DESKTOP_ASSISTANT_ACTION_ROUTES[action];
}

function isDesktopWindowAvailable(windowRef) {
  return Boolean(windowRef && !windowRef.isDestroyed());
}

function isDesktopWindowVisible(windowRef) {
  return Boolean(
    isDesktopWindowAvailable(windowRef)
    && typeof windowRef.isVisible === 'function'
    && windowRef.isVisible()
  );
}

function buildDesktopAssistantState() {
  let serviceStatus = 'starting';
  if (backendStartError
    || (backendProcess && (backendProcess.exitCode !== null || backendProcess.signalCode))) {
    serviceStatus = 'unavailable';
  } else if (desktopWebReady) {
    serviceStatus = 'ready';
  }

  return {
    serviceStatus,
    mainWindowVisible: isDesktopWindowVisible(mainWindow),
    lastReadyAt: desktopAssistantLastReadyAt,
  };
}

function notifyDesktopAssistantState() {
  if (!isDesktopWindowAvailable(assistantWindow)
    || !assistantWindow.webContents
    || (typeof assistantWindow.webContents.isDestroyed === 'function'
      && assistantWindow.webContents.isDestroyed())) {
    return false;
  }
  assistantWindow.webContents.send(
    DESKTOP_ASSISTANT_STATE_EVENT,
    buildDesktopAssistantState()
  );
  return true;
}

function isDesktopAssistantSender(event) {
  return Boolean(
    event
    && event.sender
    && isDesktopWindowAvailable(assistantWindow)
    && assistantWindow.webContents === event.sender
  );
}

function assertDesktopAssistantSender(event) {
  if (!isDesktopAssistantSender(event)) {
    throw new Error('Unauthorized desktop assistant IPC sender');
  }
}

function queueDesktopDeepLink(rawUrl, { outcome = null } = {}) {
  const route = parseDesktopDeepLink(rawUrl);
  if (!route) {
    logLine('[deep-link] rejected inbound protocol URL');
    return false;
  }
  if (pendingDesktopDeepLinkOutcome) {
    pendingDesktopDeepLinkOutcome.status = 'superseded';
  }
  pendingDesktopDeepLinkRoute = route;
  pendingDesktopDeepLinkOutcome = outcome;
  logLine(`[deep-link] accepted route path=${new URL(route, 'http://stockpulse.local').pathname}`);
  return true;
}

async function flushPendingDesktopDeepLink() {
  if (desktopDeepLinkNavigationInFlight && desktopDeepLinkFlushPromise) {
    return desktopDeepLinkFlushPromise;
  }
  if (!desktopWebReady
    || !desktopMainPageUrl
    || !pendingDesktopDeepLinkRoute
    || !mainWindow
    || mainWindow.isDestroyed()) {
    return false;
  }

  desktopDeepLinkNavigationInFlight = true;
  const flushPromise = Promise.resolve().then(async () => {
    let navigated = false;
    while (desktopWebReady
      && pendingDesktopDeepLinkRoute
      && mainWindow
      && !mainWindow.isDestroyed()) {
      const route = pendingDesktopDeepLinkRoute;
      const outcome = pendingDesktopDeepLinkOutcome;
      pendingDesktopDeepLinkRoute = null;
      pendingDesktopDeepLinkOutcome = null;
      const targetUrl = buildDesktopDeepLinkTargetUrl(desktopMainPageUrl, route);
      try {
        await mainWindow.loadURL(targetUrl);
        navigated = true;
        if (outcome) {
          outcome.status = 'navigated';
        }
        logLine(`[deep-link] routed path=${new URL(targetUrl).pathname}`);
      } catch (error) {
        if (outcome) {
          outcome.status = 'failed';
        }
        const errorName = error instanceof Error && error.name ? error.name : 'unknown_error';
        logLine(`[deep-link] route failed type=${errorName}`);
      }
    }
    return navigated;
  });
  desktopDeepLinkFlushPromise = flushPromise;
  try {
    return await flushPromise;
  } finally {
    if (desktopDeepLinkFlushPromise === flushPromise) {
      desktopDeepLinkNavigationInFlight = false;
      desktopDeepLinkFlushPromise = null;
    }
  }
}

function registerDesktopProtocolClient({
  defaultApp = Boolean(process.defaultApp),
  executablePath = process.execPath,
  argv = process.argv,
} = {}) {
  if (typeof app.setAsDefaultProtocolClient !== 'function') {
    return false;
  }
  try {
    if (defaultApp && typeof argv[1] === 'string' && argv[1]) {
      return app.setAsDefaultProtocolClient(
        DESKTOP_PROTOCOL,
        executablePath,
        [path.resolve(argv[1])]
      );
    }
    return app.setAsDefaultProtocolClient(DESKTOP_PROTOCOL);
  } catch (error) {
    logLine(`[deep-link] protocol registration failed: ${error instanceof Error ? error.message : String(error)}`);
    return false;
  }
}

function normalizeVersionString(version) {
  return String(version || '')
    .trim()
    .replace(/^v/i, '')
    .replace(/\+.*$/, '');
}

function parseSemver(version) {
  const normalized = normalizeVersionString(version);
  const match = normalized.match(/^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/);
  if (!match) {
    return null;
  }

  return {
    major: Number.parseInt(match[1], 10),
    minor: Number.parseInt(match[2], 10),
    patch: Number.parseInt(match[3], 10),
    prerelease: match[4] ? match[4].split('.') : [],
  };
}

function comparePrereleaseIdentifiers(left, right) {
  const leftIsNumeric = /^\d+$/.test(left);
  const rightIsNumeric = /^\d+$/.test(right);

  if (leftIsNumeric && rightIsNumeric) {
    const leftNumber = Number.parseInt(left, 10);
    const rightNumber = Number.parseInt(right, 10);
    if (leftNumber === rightNumber) {
      return 0;
    }
    return leftNumber > rightNumber ? 1 : -1;
  }

  if (leftIsNumeric !== rightIsNumeric) {
    return leftIsNumeric ? -1 : 1;
  }

  if (left === right) {
    return 0;
  }
  return left > right ? 1 : -1;
}

function compareVersions(leftVersion, rightVersion) {
  const left = parseSemver(leftVersion);
  const right = parseSemver(rightVersion);
  if (!left || !right) {
    return null;
  }

  for (const key of ['major', 'minor', 'patch']) {
    if (left[key] !== right[key]) {
      return left[key] > right[key] ? 1 : -1;
    }
  }

  if (!left.prerelease.length && !right.prerelease.length) {
    return 0;
  }
  if (!left.prerelease.length) {
    return 1;
  }
  if (!right.prerelease.length) {
    return -1;
  }

  const length = Math.max(left.prerelease.length, right.prerelease.length);
  for (let index = 0; index < length; index += 1) {
    const leftPart = left.prerelease[index];
    const rightPart = right.prerelease[index];
    if (leftPart === undefined) {
      return -1;
    }
    if (rightPart === undefined) {
      return 1;
    }

    const compared = comparePrereleaseIdentifiers(leftPart, rightPart);
    if (compared !== 0) {
      return compared;
    }
  }

  return 0;
}

function normalizeFiniteNumber(value, fallback = null) {
  if (value === null || value === undefined || value === '') {
    return fallback;
  }
  const numberValue = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
}

function normalizeDownloadPercent(value) {
  const percent = normalizeFiniteNumber(value);
  if (percent === null) {
    return null;
  }
  return Math.min(100, Math.max(0, Math.round(percent * 10) / 10));
}

function buildUpdateState(state = {}) {
  return {
    status: state.status || UPDATE_STATUS.IDLE,
    updateMode: state.updateMode === UPDATE_MODE.AUTO ? UPDATE_MODE.AUTO : UPDATE_MODE.MANUAL,
    currentVersion: normalizeVersionString(state.currentVersion),
    latestVersion: normalizeVersionString(state.latestVersion),
    releaseUrl:
      typeof state.releaseUrl === 'string' && state.releaseUrl.trim()
        ? state.releaseUrl.trim()
        : RELEASES_PAGE_URL,
    checkedAt: typeof state.checkedAt === 'string' ? state.checkedAt : '',
    publishedAt: typeof state.publishedAt === 'string' ? state.publishedAt : '',
    message: typeof state.message === 'string' ? state.message : '',
    releaseName: typeof state.releaseName === 'string' ? state.releaseName : '',
    tagName: typeof state.tagName === 'string' ? state.tagName : '',
    downloadPercent: normalizeDownloadPercent(state.downloadPercent),
    downloadedBytes: normalizeFiniteNumber(state.downloadedBytes),
    totalBytes: normalizeFiniteNumber(state.totalBytes),
  };
}

function extractReleaseMetadata(release) {
  if (!release || typeof release !== 'object') {
    return null;
  }

  const tagName = typeof release.tag_name === 'string' ? release.tag_name.trim() : '';
  const version = normalizeVersionString(tagName);
  if (!parseSemver(version)) {
    return null;
  }

  return {
    tagName,
    version,
    releaseName: typeof release.name === 'string' ? release.name.trim() : '',
    releaseUrl:
      typeof release.html_url === 'string' && release.html_url.trim()
        ? release.html_url.trim()
        : RELEASES_PAGE_URL,
    publishedAt: typeof release.published_at === 'string' ? release.published_at : '',
  };
}

function evaluateReleaseUpdate({ currentVersion, release, checkedAt = new Date().toISOString() }) {
  const normalizedCurrentVersion = normalizeVersionString(currentVersion);
  if (!parseSemver(normalizedCurrentVersion)) {
    return buildUpdateState({
      status: UPDATE_STATUS.ERROR,
      currentVersion: normalizedCurrentVersion,
      checkedAt,
      message: '当前桌面端版本不是有效的语义化版本，无法检查更新。',
    });
  }

  const releaseMetadata = extractReleaseMetadata(release);
  if (!releaseMetadata) {
    return buildUpdateState({
      status: UPDATE_STATUS.ERROR,
      currentVersion: normalizedCurrentVersion,
      checkedAt,
      message: 'GitHub Release 未返回可识别的语义化版本标签。',
    });
  }

  const compared = compareVersions(normalizedCurrentVersion, releaseMetadata.version);
  if (compared === null) {
    return buildUpdateState({
      status: UPDATE_STATUS.ERROR,
      currentVersion: normalizedCurrentVersion,
      latestVersion: releaseMetadata.version,
      releaseUrl: releaseMetadata.releaseUrl,
      checkedAt,
      releaseName: releaseMetadata.releaseName,
      tagName: releaseMetadata.tagName,
      message: '版本比较失败，无法判断是否存在可用更新。',
    });
  }

  if (compared < 0) {
    return buildUpdateState({
      status: UPDATE_STATUS.UPDATE_AVAILABLE,
      currentVersion: normalizedCurrentVersion,
      latestVersion: releaseMetadata.version,
      releaseUrl: releaseMetadata.releaseUrl,
      checkedAt,
      publishedAt: releaseMetadata.publishedAt,
      releaseName: releaseMetadata.releaseName,
      tagName: releaseMetadata.tagName,
      message: `发现新版本 ${releaseMetadata.version}，可前往 GitHub Releases 下载更新。`,
    });
  }

  return buildUpdateState({
    status: UPDATE_STATUS.UP_TO_DATE,
    currentVersion: normalizedCurrentVersion,
    latestVersion: releaseMetadata.version,
    releaseUrl: releaseMetadata.releaseUrl,
    checkedAt,
    publishedAt: releaseMetadata.publishedAt,
    releaseName: releaseMetadata.releaseName,
    tagName: releaseMetadata.tagName,
    message: '当前桌面端已是最新版本。',
  });
}

function fetchLatestReleaseJson({
  requestUrl = LATEST_RELEASE_API_URL,
  timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
  request = https.request,
} = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let response = null;

    const cleanupResponseListeners = () => {
      if (!response) {
        return;
      }
      response.removeAllListeners('data');
      response.removeAllListeners('end');
      response.removeAllListeners('error');
      response.removeAllListeners('aborted');
      response.removeAllListeners('close');
    };

    const finishWithError = (error) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanupResponseListeners();
      if (!req.destroyed) {
        req.destroy();
      }
      reject(error instanceof Error ? error : new Error(String(error)));
    };

    const finishWithResult = (value) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanupResponseListeners();
      resolve(value);
    };

    const req = request(
      requestUrl,
      {
        method: 'GET',
        headers: {
          Accept: 'application/vnd.github+json',
          'User-Agent': 'StockPulse-Desktop/1.0',
        },
      },
      (incomingResponse) => {
        response = incomingResponse;
        const chunks = [];

        response.on('data', (chunk) => {
          chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk)));
        });

        response.on('end', () => {
          if (settled) {
            return;
          }
          const body = Buffer.concat(chunks).toString('utf-8');
          if (response.statusCode !== 200) {
            finishWithError(new Error(`GitHub API responded with status ${response.statusCode || 'unknown'}`));
            return;
          }

          try {
            finishWithResult(JSON.parse(body));
          } catch (_error) {
            finishWithError(new Error('Failed to parse GitHub release response.'));
          }
        });

        response.on('error', (error) => {
          finishWithError(error);
        });
        response.on('aborted', () => {
          finishWithError(new Error('GitHub API response was aborted.'));
        });
        response.on('close', () => {
          if (!response.complete) {
            finishWithError(new Error('GitHub API response closed before completion.'));
          }
        });
      }
    );

    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error(`GitHub API timeout after ${timeoutMs}ms`));
    });
    req.on('error', finishWithError);
    req.end();
  });
}

async function checkForDesktopUpdates({
  currentVersion,
  timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
  fetchLatestRelease = fetchLatestReleaseJson,
} = {}) {
  const release = await fetchLatestRelease({ timeoutMs });
  return evaluateReleaseUpdate({ currentVersion, release });
}

desktopUpdateState = buildUpdateState();

function resolveEnvExamplePath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, '.env.example');
  }
  return path.join(appRootDev, '.env.example');
}

function resolvePackagedExeDir() {
  return path.dirname(app.getPath('exe'));
}

function resolveAppDir() {
  if (app.isPackaged && !isMac) {
    return resolvePackagedExeDir();
  }
  return app.getPath('userData');
}

function resolveUpdateBackupRoot() {
  return path.join(app.getPath('userData'), DESKTOP_UPDATE_BACKUP_DIR);
}

function resolveUpdateBackupManifestPath() {
  return path.join(resolveUpdateBackupRoot(), DESKTOP_UPDATE_BACKUP_MANIFEST_FILE);
}

function resolveRuntimeFileEntries(baseDir = resolveAppDir()) {
  return DESKTOP_UPDATE_RUNTIME_RELATIVE_FILES.map((relativePath) => ({
    relativePath,
    absolutePath: path.join(baseDir, relativePath),
    backupPath: path.join(resolveUpdateBackupRoot(), relativePath),
  }));
}

function readUpdateBackupManifest() {
  const manifestPath = resolveUpdateBackupManifestPath();
  if (!fs.existsSync(manifestPath)) {
    return null;
  }

  try {
    const manifestText = fs.readFileSync(manifestPath, 'utf-8');
    const manifest = JSON.parse(manifestText);
    if (!manifest || typeof manifest !== 'object') {
      return null;
    }
    return manifest;
  } catch (_error) {
    return null;
  }
}

function writeUpdateBackupManifest(manifest) {
  ensureDirectory(resolveUpdateBackupRoot());
  fs.writeFileSync(resolveUpdateBackupManifestPath(), JSON.stringify(manifest, null, 2), 'utf-8');
}

function cleanupUpdateBackupRoot() {
  try {
    fs.rmSync(resolveUpdateBackupRoot(), { recursive: true, force: true });
  } catch (_error) {
  }
}

function normalizeBackupFileList(manifest) {
  if (manifest && Array.isArray(manifest.files) && manifest.files.length) {
    return manifest.files.filter((item) => typeof item === 'string' && item.trim()).map((item) => item.trim());
  }
  return DESKTOP_UPDATE_RUNTIME_RELATIVE_FILES.slice();
}

function copyRuntimeStatePathSync(source, target) {
  const stats = fs.statSync(source);
  if (stats.isDirectory()) {
    fs.rmSync(target, { recursive: true, force: true });
    fs.mkdirSync(target, { recursive: true });
    fs.readdirSync(source, { withFileTypes: true }).forEach((entry) => {
      copyRuntimeStatePathSync(path.join(source, entry.name), path.join(target, entry.name));
    });
    return;
  }

  if (!stats.isFile()) {
    throw new Error(`unsupported runtime state path type: ${source}`);
  }

  ensureDirectory(path.dirname(target));
  fs.rmSync(target, { recursive: true, force: true });
  fs.copyFileSync(source, target);
}

function resolveLegacyProductUserDataDirs(currentUserDataDir = app.getPath('userData')) {
  const currentPath = path.resolve(currentUserDataDir);
  const parentDir = path.dirname(currentPath);
  return LEGACY_DESKTOP_PRODUCT_NAMES
    .map((productName) => path.join(parentDir, productName))
    .filter((candidate) => path.resolve(candidate) !== currentPath);
}

function readDesktopBrandMigrationRecord(targetDir) {
  const recordPath = path.join(targetDir, DESKTOP_BRAND_MIGRATION_RECORD_FILE);
  if (!fs.existsSync(recordPath)) {
    return null;
  }

  try {
    const record = JSON.parse(fs.readFileSync(recordPath, 'utf-8'));
    return record && typeof record === 'object' ? record : null;
  } catch (_error) {
    return null;
  }
}

function writeDesktopBrandMigrationRecord(result) {
  ensureDirectory(result.targetDir);
  const recordPath = path.join(result.targetDir, DESKTOP_BRAND_MIGRATION_RECORD_FILE);
  const temporaryPath = `${recordPath}.tmp`;
  fs.writeFileSync(
    temporaryPath,
    JSON.stringify({
      schemaVersion: 1,
      status: result.completed ? 'completed' : 'incomplete',
      migratedAt: new Date().toISOString(),
      sourceDir: result.sourceDir,
      targetDir: result.targetDir,
      sourcePreservedForRollback: true,
      migrated: result.migrated,
      skipped: result.skipped,
      failed: result.failed,
      rolledBack: result.rolledBack,
      rollbackFailed: result.rollbackFailed,
      usingLegacyFallback: result.usingLegacyFallback,
    }, null, 2),
    'utf-8'
  );
  fs.rmSync(recordPath, { force: true });
  fs.renameSync(temporaryPath, recordPath);
  result.recordPath = recordPath;
}

function copyLegacyUserDataFileAtomically(source, target) {
  const temporaryTarget = `${target}${DESKTOP_BRAND_MIGRATION_TEMP_SUFFIX}`;
  fs.rmSync(temporaryTarget, { force: true });
  try {
    fs.copyFileSync(source, temporaryTarget, fs.constants.COPYFILE_EXCL);
    fs.linkSync(temporaryTarget, target);
  } finally {
    fs.rmSync(temporaryTarget, { force: true });
  }
}

function copyMissingLegacyUserDataPath(source, target, relativePath, result) {
  try {
    const sourceStats = fs.lstatSync(source);
    if (sourceStats.isSymbolicLink()) {
      result.failed.push(`${relativePath} (source symbolic link is not migrated)`);
      return;
    }

    if (sourceStats.isDirectory()) {
      if (fs.existsSync(target)) {
        const targetStats = fs.lstatSync(target);
        if (targetStats.isSymbolicLink()) {
          result.skipped.push(`${relativePath} (target symbolic link)`);
          return;
        }
        if (!targetStats.isDirectory()) {
          result.failed.push(`${relativePath} (target type differs)`);
          return;
        }
      }
      ensureDirectory(target);
      fs.readdirSync(source, { withFileTypes: true }).forEach((entry) => {
        copyMissingLegacyUserDataPath(
          path.join(source, entry.name),
          path.join(target, entry.name),
          path.join(relativePath, entry.name),
          result
        );
      });
      return;
    }

    if (!sourceStats.isFile()) {
      result.skipped.push(`${relativePath} (unsupported file type)`);
      return;
    }
    if (fs.existsSync(target)) {
      const targetStats = fs.lstatSync(target);
      if (!targetStats.isFile() && !targetStats.isSymbolicLink()) {
        result.failed.push(`${relativePath} (target type differs)`);
        return;
      }
      result.skipped.push(relativePath);
      return;
    }

    ensureDirectory(path.dirname(target));
    copyLegacyUserDataFileAtomically(source, target);
    result.migrated.push(relativePath);
  } catch (error) {
    result.failed.push(`${relativePath} (${error instanceof Error ? error.message : String(error)})`);
  }
}

function rollbackCopiedLegacyUserData(result) {
  [...result.migrated].reverse().forEach((relativePath) => {
    const target = path.join(result.targetDir, relativePath);
    try {
      fs.rmSync(target, { force: true });
      result.rolledBack.push(relativePath);
    } catch (error) {
      result.rollbackFailed.push(
        `${relativePath} (${error instanceof Error ? error.message : String(error)})`
      );
    }
  });
  result.migrated = result.migrated.filter(
    (relativePath) => !result.rolledBack.includes(relativePath)
  );
}

function isCriticalLegacyMigrationFailure(failure) {
  const relativePath = String(failure).split(' (', 1)[0];
  const criticalRoots = ['.env', 'data', DESKTOP_UPDATE_BACKUP_DIR];
  return criticalRoots.some(
    (root) => relativePath === root || relativePath.startsWith(`${root}${path.sep}`)
  );
}

function migrateLegacyProductUserData({
  currentUserDataDir = app.getPath('userData'),
  legacyUserDataDirs = resolveLegacyProductUserDataDirs(currentUserDataDir),
} = {}) {
  const result = {
    sourceDir: null,
    targetDir: currentUserDataDir,
    recordPath: null,
    migrated: [],
    skipped: [],
    failed: [],
    rolledBack: [],
    rollbackFailed: [],
    completed: false,
    alreadyCompleted: false,
    usingLegacyFallback: false,
  };

  if (!app.isPackaged) {
    return result;
  }

  const sourceDir = legacyUserDataDirs.find((candidate) => fs.existsSync(candidate));
  if (!sourceDir || path.resolve(sourceDir) === path.resolve(currentUserDataDir)) {
    return result;
  }

  result.sourceDir = sourceDir;
  const existingRecord = readDesktopBrandMigrationRecord(currentUserDataDir);
  if (
    existingRecord?.status === 'completed' &&
    typeof existingRecord.sourceDir === 'string' &&
    typeof existingRecord.targetDir === 'string' &&
    path.resolve(existingRecord.sourceDir) === path.resolve(sourceDir) &&
    path.resolve(existingRecord.targetDir) === path.resolve(currentUserDataDir)
  ) {
    result.recordPath = path.join(currentUserDataDir, DESKTOP_BRAND_MIGRATION_RECORD_FILE);
    result.completed = true;
    result.alreadyCompleted = true;
    return result;
  }
  if (
    existingRecord?.status === 'incomplete' &&
    typeof existingRecord.sourceDir === 'string' &&
    path.resolve(existingRecord.sourceDir) === path.resolve(sourceDir) &&
    Array.isArray(existingRecord.rollbackFailed) &&
    existingRecord.rollbackFailed.length > 0 &&
    typeof app.setPath === 'function'
  ) {
    app.setPath('userData', sourceDir);
    result.recordPath = path.join(currentUserDataDir, DESKTOP_BRAND_MIGRATION_RECORD_FILE);
    result.failed = Array.isArray(existingRecord.failed) ? existingRecord.failed : [];
    result.rollbackFailed = existingRecord.rollbackFailed;
    result.usingLegacyFallback = true;
    return result;
  }

  LEGACY_USER_DATA_RELATIVE_PATHS.forEach((relativePath) => {
    const source = path.join(sourceDir, relativePath);
    if (!fs.existsSync(source)) {
      return;
    }
    copyMissingLegacyUserDataPath(
      source,
      path.join(currentUserDataDir, relativePath),
      relativePath,
      result
    );
  });

  result.completed = result.failed.length === 0;
  const criticalCopyFailed = result.failed.some(isCriticalLegacyMigrationFailure);
  if (criticalCopyFailed && typeof app.setPath === 'function') {
    rollbackCopiedLegacyUserData(result);
    try {
      app.setPath('userData', sourceDir);
      result.usingLegacyFallback = true;
    } catch (error) {
      result.failed.push(`[legacy fallback] ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  try {
    writeDesktopBrandMigrationRecord(result);
  } catch (error) {
    result.completed = false;
    result.failed.push(`[migration record] ${error instanceof Error ? error.message : String(error)}`);
  }

  return result;
}

function backupPackagedRuntimeState() {
  if (!isWindowsNsisInstalledApp()) {
    return;
  }

  const runtimeEntries = resolveRuntimeFileEntries();
  const backedUpFiles = [];

  cleanupUpdateBackupRoot();
  ensureDirectory(resolveUpdateBackupRoot());

  runtimeEntries.forEach(({ relativePath, absolutePath, backupPath }) => {
    if (!fs.existsSync(absolutePath)) {
      return;
    }
    copyRuntimeStatePathSync(absolutePath, backupPath);
    backedUpFiles.push(relativePath);
  });

  if (!backedUpFiles.length) {
    return;
  }

  writeUpdateBackupManifest({
    backedAt: new Date().toISOString(),
    appVersion: resolveDesktopVersion(),
    files: backedUpFiles,
  });
}

function restorePackagedRuntimeStateFromBackup() {
  const result = {
    backupRoot: null,
    restored: [],
    failed: [],
    skipped: [],
  };

  if (!isWindowsNsisInstalledApp()) {
    return result;
  }

  const manifest = readUpdateBackupManifest();
  if (!manifest) {
    return result;
  }

  const backupRoot = resolveUpdateBackupRoot();
  result.backupRoot = backupRoot;
  const backupAppVersion = normalizeVersionString(manifest.appVersion);
  const currentAppVersion = normalizeVersionString(resolveDesktopVersion());
  const versionComparison = backupAppVersion && currentAppVersion
    ? compareVersions(backupAppVersion, currentAppVersion)
    : null;
  const isSameAppVersion = Boolean(
    backupAppVersion &&
    currentAppVersion &&
    (versionComparison === 0 || (versionComparison === null && backupAppVersion === currentAppVersion))
  );
  if (isSameAppVersion) {
    const reason = `stale backup target ${backupAppVersion} was discarded because current version did not change`;
    result.skipped.push(reason);
    cleanupUpdateBackupRoot();
    logLine(`[update] discarded runtime restore backup because app version did not change after update attempt: ${currentAppVersion}`);
    return result;
  }

  const appDir = resolveAppDir();
  const runtimeEntries = resolveRuntimeFileEntries(appDir);
  const relativeFiles = normalizeBackupFileList(manifest);
  const failedRelativeFiles = [];

  try {
    relativeFiles.forEach((relativePath) => {
      try {
        const entry = runtimeEntries.find((candidate) => candidate.relativePath === relativePath);
        const source = path.join(backupRoot, relativePath);
        const target = entry ? entry.absolutePath : path.join(appDir, relativePath);
        if (!fs.existsSync(source)) {
          return;
        }
        copyRuntimeStatePathSync(source, target);
        result.restored.push(relativePath);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        failedRelativeFiles.push(relativePath);
        result.failed.push(`${relativePath} (${message})`);
      }
    });
  } finally {
    if (!result.failed.length) {
      cleanupUpdateBackupRoot();
    } else {
      try {
        writeUpdateBackupManifest({
          ...manifest,
          files: failedRelativeFiles,
          lastRestoreFailedAt: new Date().toISOString(),
        });
      } catch (error) {
        logLine(`[update] failed to rewrite pending restore manifest: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
  }

  if (result.restored.length) {
    console.log(`[update] restored runtime files from backup: ${result.restored.join(', ')}`);
  }
  if (result.failed.length) {
    logLine(`[update] skipped runtime restore files after copy failure: ${result.failed.join(', ')}`);
  }
  if (result.skipped.length) {
    logLine(`[update] skipped runtime restore: ${result.skipped.join(', ')}`);
  }

  return result;
}

function resolveMacPackagedRuntimeSourceDirs() {
  const currentExecutableDir = resolvePackagedExeDir();
  const candidates = [currentExecutableDir];
  const currentBundleDir = path.resolve(currentExecutableDir, '..', '..');
  if (path.extname(currentBundleDir).toLowerCase() === '.app') {
    const bundleParentDir = path.dirname(currentBundleDir);
    LEGACY_DESKTOP_PRODUCT_NAMES.forEach((productName) => {
      candidates.push(
        path.join(bundleParentDir, `${productName}.app`, 'Contents', 'MacOS')
      );
    });
  }

  return candidates.filter(
    (candidate, index) =>
      candidates.findIndex((item) => path.resolve(item) === path.resolve(candidate)) === index
  );
}

function migrateMacPackagedRuntimeState() {
  const result = {
    sourceDir: null,
    sourceDirs: [],
    targetDir: null,
    migrated: [],
    skipped: [],
    failed: [],
  };

  if (!app.isPackaged || !isMac) {
    return result;
  }

  const targetDir = resolveAppDir();
  result.targetDir = targetDir;

  resolveMacPackagedRuntimeSourceDirs().forEach((sourceDir) => {
    if (path.resolve(sourceDir) === path.resolve(targetDir) || !fs.existsSync(sourceDir)) {
      return;
    }
    result.sourceDirs.push(sourceDir);
    if (!result.sourceDir) {
      result.sourceDir = sourceDir;
    }

    DESKTOP_UPDATE_RUNTIME_RELATIVE_FILES.forEach((relativePath) => {
      const source = path.join(sourceDir, relativePath);
      const target = path.join(targetDir, relativePath);

      if (!fs.existsSync(source)) {
        return;
      }
      if (fs.existsSync(target)) {
        result.skipped.push(relativePath);
        return;
      }

      try {
        copyRuntimeStatePathSync(source, target);
        result.migrated.push(relativePath);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        result.failed.push(`${relativePath} (${message})`);
      }
    });
  });

  return result;
}

function resolveBackendPath() {
  if (process.env.DSA_BACKEND_PATH) {
    return process.env.DSA_BACKEND_PATH;
  }

  if (app.isPackaged) {
    const backendDir = path.join(process.resourcesPath, 'backend');
    const exeName = isWindows ? 'stock_analysis.exe' : 'stock_analysis';
    const oneDirPath = path.join(backendDir, 'stock_analysis', exeName);
    if (fs.existsSync(oneDirPath)) {
      return oneDirPath;
    }
    return path.join(backendDir, exeName);
  }

  return null;
}

function extendMacDesktopBackendPath(rawPath) {
  if (!isMac) {
    return rawPath;
  }

  const seen = new Set();
  const entries = String(rawPath || '')
    .split(DESKTOP_BACKEND_PATH_DELIMITER)
    .map((entry) => entry.trim())
    .filter(Boolean)
    .filter((entry) => {
      if (seen.has(entry)) {
        return false;
      }
      seen.add(entry);
      return true;
    });

  [...MAC_DESKTOP_CLI_PATH_ENTRIES, ...MAC_DESKTOP_SYSTEM_PATH_ENTRIES].forEach((entry) => {
    if (!seen.has(entry)) {
      entries.push(entry);
      seen.add(entry);
    }
  });

  return entries.join(DESKTOP_BACKEND_PATH_DELIMITER);
}

function normalizeBackendHost(value, fallback = '') {
  const normalized = String(value || '').trim();
  return normalized || fallback;
}

function normalizeBackendBindHost(value, fallback = DESKTOP_BACKEND_DEFAULT_HOST) {
  const host = normalizeBackendHost(value, fallback);
  const lowerHost = host.toLowerCase();
  if (lowerHost === '*') {
    return '0.0.0.0';
  }
  if (lowerHost === '[::]') {
    return '::';
  }
  return host;
}

function hasOwnValue(object, key) {
  return Object.prototype.hasOwnProperty.call(object || {}, key);
}

function parseQuotedEnvValue(value, quote) {
  let result = '';
  for (let index = 1; index < value.length; index += 1) {
    const char = value[index];
    if (char === quote) {
      if (quote === '"') {
        return result.replace(/\\([nrt"\\$])/g, (_match, escaped) => {
          if (escaped === 'n') {
            return '\n';
          }
          if (escaped === 'r') {
            return '\r';
          }
          if (escaped === 't') {
            return '\t';
          }
          return escaped;
        });
      }
      return result.replace(/\\'/g, "'").replace(/\\\\/g, '\\');
    }
    result += char;
  }

  return value.trim();
}

function parseEnvScalarValue(rawValue) {
  const value = String(rawValue || '').trimStart();
  if (!value) {
    return '';
  }

  const quote = value[0];
  if (quote === '"' || quote === "'") {
    return parseQuotedEnvValue(value, quote);
  }

  for (let index = 0; index < value.length; index += 1) {
    if (value[index] === '#' && (index === 0 || /\s/.test(value[index - 1]))) {
      return value.slice(0, index).trim();
    }
  }

  return value.trim();
}

function expandEnvReferences(value, values = {}, sourceEnv = process.env) {
  return String(value || '').replace(
    /\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}/g,
    (_match, name, defaultValue) => {
      if (hasOwnValue(sourceEnv, name)) {
        return String(sourceEnv[name]);
      }
      if (hasOwnValue(values, name)) {
        return String(values[name]);
      }
      return defaultValue === undefined ? '' : defaultValue;
    }
  );
}

function readEnvFileValues(envFile, sourceEnv = process.env) {
  if (!envFile || !fs.existsSync(envFile)) {
    return {};
  }

  let content = '';
  try {
    content = fs.readFileSync(envFile, 'utf-8');
  } catch (_error) {
    return {};
  }

  const values = {};
  for (const line of content.split(/\r?\n/)) {
    const match = line.match(/^\uFEFF?\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!match) {
      continue;
    }
    values[match[1]] = expandEnvReferences(
      parseEnvScalarValue(match[2]),
      values,
      sourceEnv
    );
  }

  return values;
}

function readEnvFileValue(envFile, key, sourceEnv = process.env) {
  const values = readEnvFileValues(envFile, sourceEnv);
  return hasOwnValue(values, key) ? values[key] : null;
}

function resolveDesktopProviderDailyCacheDir({
  envFile,
  dbPath,
  sourceEnv = process.env,
} = {}) {
  const sourceValue = hasOwnValue(sourceEnv, PROVIDER_DAILY_CACHE_DIR_ENV_KEY)
    ? String(sourceEnv[PROVIDER_DAILY_CACHE_DIR_ENV_KEY] || '').trim()
    : '';
  if (sourceValue) {
    return sourceValue;
  }

  const envFileValue = String(
    readEnvFileValue(envFile, PROVIDER_DAILY_CACHE_DIR_ENV_KEY, sourceEnv) || ''
  ).trim();
  if (envFileValue) {
    return envFileValue;
  }

  return path.join(path.dirname(dbPath), 'provider_cache', 'daily');
}

function resolveBackendBindHost({
  envFile,
  sourceEnv = process.env,
  fallback = DESKTOP_BACKEND_DEFAULT_HOST,
} = {}) {
  const sourceHost = normalizeBackendHost(sourceEnv.WEBUI_HOST);
  if (sourceHost) {
    return normalizeBackendBindHost(sourceHost, fallback);
  }

  const envFileHost = normalizeBackendHost(readEnvFileValue(envFile, 'WEBUI_HOST', sourceEnv));
  return normalizeBackendBindHost(envFileHost || fallback, fallback);
}

function resolveDesktopConnectHost(bindHost) {
  const host = normalizeBackendBindHost(bindHost, DESKTOP_BACKEND_DEFAULT_HOST);
  if (PUBLIC_BIND_HOSTS.has(host.toLowerCase())) {
    return DESKTOP_BACKEND_DEFAULT_HOST;
  }
  return host;
}

function formatUrlHost(host) {
  const normalized = normalizeBackendHost(host, DESKTOP_BACKEND_DEFAULT_HOST);
  if (normalized.startsWith('[') && normalized.endsWith(']')) {
    return normalized;
  }
  return normalized.includes(':') ? `[${normalized}]` : normalized;
}

function buildBackendUrl(host, port, pathname = '/') {
  const url = new URL(`http://${formatUrlHost(host)}:${port}/`);
  url.pathname = pathname;
  return url.toString();
}

function buildBackendArgs({ host, port }) {
  return [
    '--serve-only',
    '--host',
    normalizeBackendBindHost(host, DESKTOP_BACKEND_DEFAULT_HOST),
    '--port',
    String(port),
  ];
}

function buildBackendEnvironment({
  envFile,
  dbPath,
  logDir,
  port = null,
  host = null,
  sourceEnv = process.env,
}) {
  const selectedPort = Number(port);
  const selectedHost = normalizeBackendBindHost(
    normalizeBackendHost(host) || resolveBackendBindHost({ envFile, sourceEnv }),
    DESKTOP_BACKEND_DEFAULT_HOST
  );
  const env = {
    ...sourceEnv,
    DSA_DESKTOP_MODE: 'true',
    ENV_FILE: envFile,
    DATABASE_PATH: dbPath,
    LOG_DIR: logDir,
    PROVIDER_DAILY_CACHE_DIR: resolveDesktopProviderDailyCacheDir({
      envFile,
      dbPath,
      sourceEnv,
    }),
    PYTHONUTF8: '1',
    PYTHONIOENCODING: 'utf-8',
    WEBUI_HOST: selectedHost,
    WEBUI_ENABLED: 'false',
    BOT_ENABLED: 'false',
    DINGTALK_STREAM_ENABLED: 'false',
    FEISHU_STREAM_ENABLED: 'false',
  };

  if (Number.isInteger(selectedPort) && selectedPort >= 1 && selectedPort <= 65535) {
    env.WEBUI_PORT = String(selectedPort);
  }

  if (isMac) {
    env.PATH = extendMacDesktopBackendPath(sourceEnv.PATH);
  }

  return env;
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function ensureDirectory(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

function initLogging() {
  const appDir = resolveAppDir();
  logFilePath = path.join(appDir, 'logs', 'desktop.log');
  
  // Ensure the log directory exists
  const logDir = path.dirname(logFilePath);
  ensureDirectory(logDir);
  
  logLine('Desktop app starting');
}

function logLine(message) {
  const timestamp = new Date().toISOString();
  const line = `[${timestamp}] ${message}\n`;
  try {
    if (logFilePath) {
      fs.appendFileSync(logFilePath, line, 'utf-8');
    }
  } catch (error) {
    console.error(error);
  }
  console.log(line.trim());
}

function decodeBackendOutput(data, decoder) {
  if (typeof data === 'string') {
    return data.trim();
  }
  if (!Buffer.isBuffer(data)) {
    return String(data).trim();
  }

  let decoded = decoder.decode(data, { stream: true });

  // Windows consoles and subprocesses may emit local-code-page bytes; fall back to GBK when replacement characters indicate a decode failure.
  if (isWindows && decoded.includes('\uFFFD')) {
    try {
      decoded = new TextDecoder('gbk', { fatal: false }).decode(data, { stream: true });
    } catch (_error) {
    }
  }

  return decoded.trim();
}

function formatCommand(command, args = []) {
  return [command, ...args]
    .map((part) => {
      const value = String(part);
      return value.includes(' ') ? `"${value}"` : value;
    })
    .join(' ');
}

function resolvePythonPath() {
  return process.env.DSA_PYTHON || 'python';
}

function ensureEnvFile(envPath) {
  if (fs.existsSync(envPath)) {
    return;
  }

  const envExample = resolveEnvExamplePath();
  if (fs.existsSync(envExample)) {
    fs.copyFileSync(envExample, envPath);
    return;
  }

  fs.writeFileSync(envPath, '# Configure your API keys and stock list here.\n', 'utf-8');
}

function findAvailablePort(startPort = 8000, endPort = 8100, host = DESKTOP_BACKEND_DEFAULT_HOST) {
  const bindHost = normalizeBackendBindHost(host, DESKTOP_BACKEND_DEFAULT_HOST);
  return new Promise((resolve, reject) => {
    const tryPort = (port) => {
      if (port > endPort) {
        reject(new Error('No available port'));
        return;
      }

      const server = net.createServer();
      server.once('error', () => {
        tryPort(port + 1);
      });
      server.once('listening', () => {
        server.close(() => resolve(port));
      });
      server.listen(port, bindHost);
    };

    tryPort(startPort);
  });
}

function waitForHealth(
  url,
  timeoutMs = 60000,
  intervalMs = 250,
  requestTimeoutMs = 1500,
  shouldAbort = null,
  onProgress = null
) {
  const start = Date.now();
  let attempts = 0;

  return new Promise((resolve, reject) => {
    let settled = false;
    let retryTimer = null;
    let activeRequest = null;

    const emitProgress = (payload) => {
      if (typeof onProgress !== 'function') {
        return;
      }
      try {
        onProgress(payload);
      } catch (_error) {
      }
    };

    const finish = (error, result) => {
      if (settled) {
        return;
      }
      settled = true;

      if (retryTimer) {
        clearTimeout(retryTimer);
        retryTimer = null;
      }

      if (activeRequest && !activeRequest.destroyed) {
        activeRequest.destroy();
      }

      if (error) {
        emitProgress({
          type: 'final_error',
          elapsedMs: Date.now() - start,
          attempts,
          message: error.message,
        });
      }

      if (error) {
        reject(error);
      } else {
        resolve(result);
      }
    };

    const scheduleNext = () => {
      if (settled) {
        return;
      }
      retryTimer = setTimeout(attempt, intervalMs);
    };

    const attempt = () => {
      if (settled) {
        return;
      }

      if (typeof shouldAbort === 'function') {
        const abortReason = shouldAbort();
        if (abortReason) {
          emitProgress({
            type: 'aborted',
            elapsedMs: Date.now() - start,
            attempts,
            reason: abortReason,
          });
          finish(new Error(`Health check aborted: ${abortReason}`));
          return;
        }
      }

      const elapsedMs = Date.now() - start;
      if (elapsedMs > timeoutMs) {
        emitProgress({
          type: 'total_timeout',
          elapsedMs,
          attempts,
          timeoutMs,
        });
        finish(new Error(`Health check timeout after ${elapsedMs}ms`));
        return;
      }

      attempts += 1;
      emitProgress({
        type: 'probe_start',
        elapsedMs,
        attempts,
      });

      activeRequest = http.get(url, (res) => {
        if (settled) {
          return;
        }

        res.resume();
        if (res.statusCode === 200) {
          const readyElapsedMs = Date.now() - start;
          emitProgress({
            type: 'ready',
            elapsedMs: readyElapsedMs,
            attempts,
          });
          finish(null, { elapsedMs: readyElapsedMs, attempts });
          return;
        }

        emitProgress({
          type: 'probe_status',
          elapsedMs: Date.now() - start,
          attempts,
          statusCode: res.statusCode,
        });
        scheduleNext();
      });

      activeRequest.setTimeout(requestTimeoutMs, () => {
        emitProgress({
          type: 'probe_timeout',
          elapsedMs: Date.now() - start,
          attempts,
          requestTimeoutMs,
        });
        activeRequest.destroy(new Error(`Health probe request timeout after ${requestTimeoutMs}ms`));
      });

      activeRequest.on('error', (error) => {
        if (settled) {
          return;
        }

        emitProgress({
          type: 'probe_error',
          elapsedMs: Date.now() - start,
          attempts,
          errorCode: error.code || 'unknown',
          errorMessage: error.message,
        });
        scheduleNext();
      });
    };

    attempt();
  });
}

function startBackend({ port, envFile, dbPath, logDir, host = null }) {
  const backendPath = resolveBackendPath();
  backendStartError = null;
  const launchStartedAt = Date.now();
  const bindHost = normalizeBackendBindHost(
    normalizeBackendHost(host) || resolveBackendBindHost({ envFile }),
    DESKTOP_BACKEND_DEFAULT_HOST
  );

  const env = buildBackendEnvironment({ envFile, dbPath, logDir, port, host: bindHost });

  const args = buildBackendArgs({ host: bindHost, port });
  let launchMode = '';
  let launchCommand = '';
  let launchCwd = '';

  if (backendPath) {
    if (!fs.existsSync(backendPath)) {
      throw new Error(`Backend executable not found: ${backendPath}`);
    }
    launchMode = 'packaged';
    launchCommand = formatCommand(backendPath, args);
    launchCwd = path.dirname(backendPath);
    backendProcess = spawn(backendPath, args, {
      env,
      cwd: launchCwd,
      stdio: 'pipe',
      windowsHide: true,
    });
  } else {
    const pythonPath = resolvePythonPath();
    const scriptPath = path.join(appRootDev, 'main.py');
    const pythonArgs = ['-X', 'utf8', scriptPath, ...args];
    launchMode = 'development';
    launchCommand = formatCommand(pythonPath, pythonArgs);
    launchCwd = appRootDev;
    backendProcess = spawn(pythonPath, pythonArgs, {
      env,
      cwd: launchCwd,
      stdio: 'pipe',
      windowsHide: true,
    });
  }

  if (backendProcess) {
    const launchedProcess = backendProcess;
    let firstStdoutLogged = false;
    let firstStderrLogged = false;
    const stdoutDecoder = new TextDecoder('utf-8', { fatal: false });
    const stderrDecoder = new TextDecoder('utf-8', { fatal: false });

    launchedProcess.once('spawn', () => {
      if (backendProcess !== launchedProcess) {
        return;
      }
      logLine(`[backend] spawned pid=${launchedProcess.pid} in ${Date.now() - launchStartedAt}ms`);
    });
    launchedProcess.on('error', (error) => {
      if (backendProcess !== launchedProcess) {
        return;
      }
      backendStartError = error;
      desktopWebReady = false;
      logLine(`[backend] failed to start: ${error.message}`);
      notifyDesktopAssistantState();
    });
    launchedProcess.stdout.on('data', (data) => {
      if (backendProcess !== launchedProcess) {
        return;
      }
      if (!firstStdoutLogged) {
        firstStdoutLogged = true;
        logLine(`[backend] first stdout after ${Date.now() - launchStartedAt}ms`);
      }
      logLine(`[backend] ${decodeBackendOutput(data, stdoutDecoder)}`);
    });
    launchedProcess.stderr.on('data', (data) => {
      if (backendProcess !== launchedProcess) {
        return;
      }
      if (!firstStderrLogged) {
        firstStderrLogged = true;
        logLine(`[backend] first stderr after ${Date.now() - launchStartedAt}ms`);
      }
      logLine(`[backend] ${decodeBackendOutput(data, stderrDecoder)}`);
    });
    launchedProcess.on('exit', (code, signal) => {
      if (backendProcess !== launchedProcess) {
        return;
      }
      desktopWebReady = false;
      if (!desktopIsQuitting && !backendStartError) {
        backendStartError = new Error('Backend process exited');
      }
      logLine(`[backend] exited with code ${code}, signal ${signal || 'none'}`);
      notifyDesktopAssistantState();
    });
  }

  return {
    mode: launchMode,
    command: launchCommand,
    cwd: launchCwd,
  };
}

function waitForBackendExit(processRef, timeoutMs = 5000) {
  if (!processRef || processRef.exitCode !== null || processRef.signalCode) {
    return Promise.resolve(true);
  }

  return new Promise((resolve) => {
    let settled = false;
    let timer = null;
    let onExit = null;

    const done = (exited) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      if (onExit) {
        processRef.removeListener('exit', onExit);
      }
      resolve(exited || processRef.exitCode !== null || Boolean(processRef.signalCode));
    };

    onExit = () => done(true);

    timer = setTimeout(() => {
      done(false);
    }, timeoutMs);

    processRef.once('exit', onExit);
  });
}

function __setBackendProcessForTest(processRef = null) {
  backendProcess = processRef;
}

function clearBackendProcessIfCurrent(processRef) {
  if (backendProcess === processRef) {
    backendProcess = null;
  }
}

function stopBackend() {
  if (!backendProcess) {
    return Promise.resolve();
  }
  const processToStop = backendProcess;
  if (processToStop.exitCode !== null || processToStop.signalCode) {
    clearBackendProcessIfCurrent(processToStop);
    return Promise.resolve();
  }

  const waitAndClear = () => waitForBackendExit(processToStop, 10000)
    .then((exited) => {
      if (!exited) {
        return;
      }
      clearBackendProcessIfCurrent(processToStop);
    });

  if (isWindows) {
    spawn('taskkill', ['/PID', String(processToStop.pid), '/T', '/F'], { windowsHide: true }).on('error', () => {
    });
    return waitAndClear();
  }

  if (!processToStop.killed) {
    processToStop.kill('SIGTERM');
  }
  setTimeout(() => {
    if (processToStop.killed || processToStop.exitCode !== null || processToStop.signalCode) {
      return;
    }
    try {
      processToStop.kill('SIGKILL');
    } catch (_error) {
    }
  }, 3000);

  return waitAndClear();
}

function resolveDesktopVersion() {
  return String(app.getVersion() || '').trim();
}

function buildMainPageUrl(port, timestamp = Date.now(), host = DESKTOP_BACKEND_DEFAULT_HOST) {
  const url = new URL(buildBackendUrl(host, port, '/'));
  url.searchParams.set('desktop_version', resolveDesktopVersion() || 'unknown');
  url.searchParams.set('cache_bust', String(timestamp));
  return url.toString();
}

function isWindowsNsisInstalledApp() {
  if (!isWindows || !app.isPackaged) {
    return false;
  }

  const appDir = path.dirname(app.getPath('exe'));
  return WINDOWS_NSIS_UNINSTALLER_NAMES.some((name) => fs.existsSync(path.join(appDir, name)));
}

function getElectronAutoUpdater() {
  if (electronAutoUpdater !== undefined) {
    return electronAutoUpdater;
  }

  if (!isWindowsNsisInstalledApp()) {
    electronAutoUpdater = null;
    return electronAutoUpdater;
  }

  try {
    electronAutoUpdater = require('electron-updater').autoUpdater;
  } catch (error) {
    electronAutoUpdater = null;
    logLine(`[update] electron-updater unavailable: ${error instanceof Error ? error.message : String(error)}`);
  }

  return electronAutoUpdater;
}

function canUseElectronAutoUpdater() {
  return Boolean(getElectronAutoUpdater());
}

function resolveReleasePageUrlForVersion(version) {
  const normalizedVersion = normalizeVersionString(version);
  if (!normalizedVersion) {
    return RELEASES_PAGE_URL;
  }
  return `${RELEASES_PAGE_URL}/tag/v${normalizedVersion}`;
}

function resolveUpdaterLatestVersion(updateInfo = {}) {
  return normalizeVersionString(updateInfo.version || updateInfo.tag || updateInfo.releaseName);
}

function buildElectronUpdaterState(status, updateInfo = {}, extraState = {}) {
  const latestVersion = normalizeVersionString(extraState.latestVersion || resolveUpdaterLatestVersion(updateInfo));
  return buildUpdateState({
    status,
    updateMode: UPDATE_MODE.AUTO,
    currentVersion: resolveDesktopVersion(),
    latestVersion,
    releaseUrl: resolveReleasePageUrlForVersion(latestVersion),
    publishedAt: typeof updateInfo.releaseDate === 'string' ? updateInfo.releaseDate : '',
    releaseName: typeof updateInfo.releaseName === 'string' ? updateInfo.releaseName : '',
    tagName: latestVersion ? `v${latestVersion}` : '',
    ...extraState,
  });
}

function sanitizeReleaseUrl(candidateUrl) {
  if (typeof candidateUrl !== 'string' || !candidateUrl.trim()) {
    return RELEASES_PAGE_URL;
  }

  try {
    const parsed = new URL(candidateUrl.trim());
    const allowedReleasePathPrefix = `/${GITHUB_OWNER}/${GITHUB_REPO}/releases`;
    const isGithubHost = parsed.origin === 'https://github.com';
    const isRepositoryReleasePath =
      parsed.pathname === allowedReleasePathPrefix ||
      parsed.pathname.startsWith(`${allowedReleasePathPrefix}/`);
    return isGithubHost && isRepositoryReleasePath ? parsed.toString() : RELEASES_PAGE_URL;
  } catch (_error) {
    return RELEASES_PAGE_URL;
  }
}

function broadcastDesktopUpdateState() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  mainWindow.webContents.send('desktop:update-state', desktopUpdateState);
}

function setDesktopUpdateState(nextState) {
  desktopUpdateState = buildUpdateState({
    currentVersion: resolveDesktopVersion(),
    ...nextState,
  });
  broadcastDesktopUpdateState();
  return desktopUpdateState;
}

async function maybePromptDesktopUpdate(state) {
  if (!state || state.status !== UPDATE_STATUS.UPDATE_AVAILABLE) {
    return;
  }
  if (state.updateMode === UPDATE_MODE.AUTO) {
    return;
  }
  if (!state.latestVersion || state.latestVersion === lastNotifiedUpdateVersion) {
    return;
  }
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  lastNotifiedUpdateVersion = state.latestVersion;
  const currentVersion = state.currentVersion || resolveDesktopVersion() || '当前版本';
  const result = await dialog.showMessageBox(mainWindow, {
    type: 'info',
    buttons: ['稍后', '前往下载'],
    defaultId: 1,
    cancelId: 0,
    title: '发现新版本',
    message: `检测到桌面端新版本 ${state.latestVersion}`,
    detail: `当前版本 ${currentVersion}。新版本将跳转到 GitHub Releases 下载页，不会静默下载或自动安装。`,
    noLink: true,
  });

  if (result.response === 1) {
    await shell.openExternal(sanitizeReleaseUrl(state.releaseUrl));
  }
}

async function installDownloadedUpdate() {
  const updater = getElectronAutoUpdater();
  if (!updater) {
    throw new Error('当前运行模式不支持自动安装更新。');
  }
  if (desktopUpdateState?.status !== UPDATE_STATUS.UPDATE_DOWNLOADED) {
    throw new Error('更新尚未下载完成，无法自动安装。');
  }

  setDesktopUpdateState({
    status: UPDATE_STATUS.INSTALLING,
    updateMode: UPDATE_MODE.AUTO,
    latestVersion: desktopUpdateState?.latestVersion || '',
    releaseUrl: desktopUpdateState?.releaseUrl || RELEASES_PAGE_URL,
    message: '正在重启并安装更新...',
  });
  let backupRoot = null;
  try {
    logLine('[update] stop backend and backup runtime data before install');
    await stopBackend();
    backupRoot = resolveUpdateBackupRoot();
    cleanupUpdateBackupRoot();

    for (let attempt = 1; attempt <= 3; attempt += 1) {
      try {
        backupPackagedRuntimeState();
        break;
      } catch (error) {
        if (attempt === 3) {
          setDesktopUpdateState({
            status: UPDATE_STATUS.ERROR,
            updateMode: UPDATE_MODE.AUTO,
            currentVersion: resolveDesktopVersion(),
            latestVersion: desktopUpdateState?.latestVersion || '',
            releaseUrl: desktopUpdateState?.releaseUrl || RELEASES_PAGE_URL,
            checkedAt: new Date().toISOString(),
            message: `更新安装准备失败：${error instanceof Error ? error.message : String(error)}`,
          });
          throw error;
        }

        await sleep(300 * attempt);
      }
    }

    logLine('[update] silent quit and install requested');
    updater.quitAndInstall(true, true);
    return true;
  } catch (error) {
    if (backupRoot) {
      cleanupUpdateBackupRoot();
    }
    logLine(`[update] install downloaded update failed: ${error instanceof Error ? error.message : String(error)}`);
    throw error;
  }
}

async function maybePromptInstallDownloadedUpdate(state) {
  if (!state || state.status !== UPDATE_STATUS.UPDATE_DOWNLOADED || state.updateMode !== UPDATE_MODE.AUTO) {
    return;
  }
  if (!state.latestVersion || state.latestVersion === lastPromptedInstallVersion) {
    return;
  }
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  lastPromptedInstallVersion = state.latestVersion;
  const result = await dialog.showMessageBox(mainWindow, {
    type: 'info',
    buttons: ['稍后', '立即重启安装'],
    defaultId: 1,
    cancelId: 0,
    title: '更新已下载',
    message: `桌面端新版本 ${state.latestVersion} 已下载`,
    detail: '重启应用后会自动完成安装。未保存的设置草稿请先保存。',
    noLink: true,
  });

  if (result.response === 1) {
    try {
      await installDownloadedUpdate();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      logLine(`[update] auto install prompt failed: ${message}`);
      setDesktopUpdateState({
        status: UPDATE_STATUS.ERROR,
        updateMode: UPDATE_MODE.AUTO,
        currentVersion: resolveDesktopVersion(),
        latestVersion: state.latestVersion || desktopUpdateState?.latestVersion || '',
        releaseUrl: state.releaseUrl || desktopUpdateState?.releaseUrl || RELEASES_PAGE_URL,
        checkedAt: new Date().toISOString(),
        message: `更新安装失败：${message}。可先保存草稿并前往下载页，或稍后重试。`,
      });
    }
  }
}

function configureElectronAutoUpdater() {
  const updater = getElectronAutoUpdater();
  if (!updater || electronAutoUpdaterConfigured) {
    return updater;
  }

  updater.autoDownload = true;
  updater.autoInstallOnAppQuit = false;
  if (isWindows && app.isPackaged) {
    const installDirectory = path.dirname(app.getPath('exe'));
    if (installDirectory) {
      updater.installDirectory = installDirectory;
      logLine(`[update] auto updater install directory set to ${updater.installDirectory}`);
    }
  }

  updater.on('checking-for-update', () => {
    setDesktopUpdateState({
      status: UPDATE_STATUS.CHECKING,
      updateMode: UPDATE_MODE.AUTO,
      currentVersion: resolveDesktopVersion(),
      message: '正在检查桌面端更新...',
    });
  });

  updater.on('update-available', (info = {}) => {
    const latestVersion = resolveUpdaterLatestVersion(info) || '最新版本';
    const nextState = buildElectronUpdaterState(UPDATE_STATUS.UPDATE_AVAILABLE, info, {
      message: `发现新版本 ${latestVersion}，正在后台下载更新...`,
    });
    setDesktopUpdateState(nextState);
    logLine(`[update] auto update available latest=${nextState.latestVersion || 'unknown'}`);
  });

  updater.on('update-not-available', (info = {}) => {
    const nextState = buildElectronUpdaterState(UPDATE_STATUS.UP_TO_DATE, info, {
      message: '当前桌面端已是最新版本。',
    });
    setDesktopUpdateState(nextState);
    logLine(`[update] auto update not available current=${nextState.currentVersion || 'unknown'}`);
  });

  updater.on('download-progress', (progress = {}) => {
    const percent = normalizeDownloadPercent(progress.percent);
    const nextState = setDesktopUpdateState({
      status: UPDATE_STATUS.DOWNLOADING,
      updateMode: UPDATE_MODE.AUTO,
      latestVersion: desktopUpdateState?.latestVersion || '',
      releaseUrl: desktopUpdateState?.releaseUrl || RELEASES_PAGE_URL,
      downloadPercent: percent,
      downloadedBytes: progress.transferred,
      totalBytes: progress.total,
      message:
        percent === null
          ? '正在下载桌面端更新...'
          : `正在下载桌面端更新（${percent.toFixed(percent % 1 === 0 ? 0 : 1)}%）...`,
    });
    logLine(`[update] download progress percent=${nextState.downloadPercent ?? 'unknown'}`);
  });

  updater.on('update-downloaded', (info = {}) => {
    const latestVersion = resolveUpdaterLatestVersion(info) || desktopUpdateState?.latestVersion || '';
    const nextState = buildElectronUpdaterState(UPDATE_STATUS.UPDATE_DOWNLOADED, info, {
      latestVersion,
      downloadPercent: 100,
      message: latestVersion
        ? `新版本 ${latestVersion} 已下载，可重启应用完成安装。`
        : '新版本已下载，可重启应用完成安装。',
    });
    setDesktopUpdateState(nextState);
    logLine(`[update] downloaded latest=${nextState.latestVersion || 'unknown'}`);
    void maybePromptInstallDownloadedUpdate(nextState);
  });

  updater.on('error', (error) => {
    const message = error instanceof Error ? error.message : String(error);
    logLine(`[update] auto updater failed: ${message}`);
    setDesktopUpdateState({
      status: UPDATE_STATUS.ERROR,
      updateMode: UPDATE_MODE.AUTO,
      currentVersion: resolveDesktopVersion(),
      latestVersion: desktopUpdateState?.latestVersion || '',
      releaseUrl: desktopUpdateState?.releaseUrl || RELEASES_PAGE_URL,
      checkedAt: new Date().toISOString(),
      message: `自动更新失败：${message}`,
    });
  });

  electronAutoUpdaterConfigured = true;
  return updater;
}

async function performElectronUpdaterCheck({ manual = false } = {}) {
  const updater = configureElectronAutoUpdater();
  if (!updater) {
    throw new Error('当前平台不支持自动安装更新。');
  }
  if (electronUpdateCheckInFlight) {
    return desktopUpdateState;
  }

  electronUpdateCheckInFlight = true;
  setDesktopUpdateState({
    status: UPDATE_STATUS.CHECKING,
    updateMode: UPDATE_MODE.AUTO,
    currentVersion: resolveDesktopVersion(),
    message: manual ? '正在检查桌面端更新...' : '正在后台检查桌面端更新...',
  });

  try {
    await updater.checkForUpdates();
    return desktopUpdateState;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logLine(`[update] auto updater check failed: ${message}`);
    const nextState = setDesktopUpdateState({
      status: manual ? UPDATE_STATUS.ERROR : UPDATE_STATUS.IDLE,
      updateMode: UPDATE_MODE.AUTO,
      currentVersion: resolveDesktopVersion(),
      checkedAt: new Date().toISOString(),
      message: manual ? `检查更新失败：${message}` : '',
    });
    return nextState;
  } finally {
    electronUpdateCheckInFlight = false;
  }
}

async function performDesktopUpdateCheck({ manual = false, notify = false } = {}) {
  if (canUseElectronAutoUpdater()) {
    return performElectronUpdaterCheck({ manual, notify });
  }

  const currentVersion = resolveDesktopVersion();
  setDesktopUpdateState({
    status: UPDATE_STATUS.CHECKING,
    currentVersion,
    message: manual ? '正在检查桌面端更新...' : '正在后台检查桌面端更新...',
  });

  try {
    const nextState = await checkForDesktopUpdates({ currentVersion });
    const resolvedState = setDesktopUpdateState(nextState);
    logLine(
      `[update] status=${resolvedState.status} current=${resolvedState.currentVersion || 'unknown'} latest=${resolvedState.latestVersion || 'unknown'}`
    );
    if (notify) {
      await maybePromptDesktopUpdate(resolvedState);
    }
    return resolvedState;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logLine(`[update] check failed: ${message}`);

    if (manual) {
      return setDesktopUpdateState({
        status: UPDATE_STATUS.ERROR,
        currentVersion,
        checkedAt: new Date().toISOString(),
        message: `检查更新失败：${message}`,
      });
    }

    return setDesktopUpdateState({
      status: UPDATE_STATUS.IDLE,
      currentVersion,
      checkedAt: new Date().toISOString(),
      message: '',
    });
  }
}

function resolveDesktopAssistantTrayIconPath({
  packaged = app.isPackaged,
  resourcesPath = process.resourcesPath,
} = {}) {
  if (packaged) {
    return path.join(resourcesPath, 'assistant-tray.png');
  }
  return path.resolve(
    __dirname,
    '..',
    '..',
    'docs',
    'assets',
    'dsa_vi',
    'lightlogo.iconset',
    'icon_32x32.png'
  );
}

function isDesktopTrayAvailable() {
  return Boolean(
    desktopTray
    && (typeof desktopTray.isDestroyed !== 'function' || !desktopTray.isDestroyed())
  );
}

function hideExistingMainWindow() {
  if (!isDesktopWindowAvailable(mainWindow) || typeof mainWindow.hide !== 'function') {
    return false;
  }
  mainWindow.hide();
  notifyDesktopAssistantState();
  return true;
}

function handleMainWindowClose(event) {
  if (desktopIsQuitting || !isDesktopTrayAvailable() || !isDesktopWindowAvailable(mainWindow)) {
    return false;
  }
  if (event && typeof event.preventDefault === 'function') {
    event.preventDefault();
  }
  hideExistingMainWindow();
  return true;
}

async function openDesktopAssistantAction(action, rawStockCode = '') {
  const route = buildDesktopAssistantRoute(action, rawStockCode);
  if (!route) {
    return { ok: false, error: 'invalid-action' };
  }
  if (!isDesktopWindowAvailable(mainWindow)) {
    return { ok: false, error: 'main-window-unavailable' };
  }

  const rawUrl = `${DESKTOP_PROTOCOL}://${DESKTOP_PROTOCOL_HOST}${route}`;
  const navigationOutcome = { status: 'pending' };
  if (!queueDesktopDeepLink(rawUrl, { outcome: navigationOutcome })) {
    return { ok: false, error: 'route-rejected' };
  }

  focusExistingMainWindow();
  await flushPendingDesktopDeepLink();
  if (navigationOutcome.status === 'failed') {
    return { ok: false, error: 'navigation-failed' };
  }
  if (navigationOutcome.status === 'superseded') {
    return { ok: false, error: 'navigation-superseded' };
  }
  return {
    ok: true,
    pending: navigationOutcome.status === 'pending',
  };
}

async function createDesktopAssistantWindow({ BrowserWindowClass = BrowserWindow } = {}) {
  if (isDesktopWindowAvailable(assistantWindow)) {
    return assistantWindowLoadPromise || assistantWindow;
  }

  const createdWindow = new BrowserWindowClass({
    width: DESKTOP_ASSISTANT_WINDOW_WIDTH,
    height: DESKTOP_ASSISTANT_WINDOW_HEIGHT,
    minWidth: DESKTOP_ASSISTANT_WINDOW_WIDTH,
    maxWidth: DESKTOP_ASSISTANT_WINDOW_WIDTH,
    minHeight: DESKTOP_ASSISTANT_WINDOW_HEIGHT,
    maxHeight: DESKTOP_ASSISTANT_WINDOW_HEIGHT,
    useContentSize: true,
    frame: false,
    alwaysOnTop: true,
    resizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    show: false,
    title: 'StockPulse Assistant',
    backgroundColor: resolveWindowBackgroundColor(),
    webPreferences: {
      preload: path.join(__dirname, 'assistant-preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  assistantWindow = createdWindow;

  createdWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  const denyRendererNavigation = (event) => {
    event.preventDefault();
  };
  createdWindow.webContents.on('will-navigate', denyRendererNavigation);
  createdWindow.webContents.on('will-redirect', denyRendererNavigation);
  createdWindow.on('close', (event) => {
    if (desktopIsQuitting) {
      return;
    }
    if (event && typeof event.preventDefault === 'function') {
      event.preventDefault();
    }
    createdWindow.hide();
    notifyDesktopAssistantState();
  });
  createdWindow.on('show', notifyDesktopAssistantState);
  createdWindow.on('hide', notifyDesktopAssistantState);
  createdWindow.once('closed', () => {
    if (assistantWindow === createdWindow) {
      assistantWindow = null;
      assistantWindowLoadPromise = null;
    }
  });

  const assistantPath = path.join(__dirname, 'renderer', 'assistant.html');
  assistantWindowLoadPromise = Promise.resolve(createdWindow.loadFile(assistantPath))
    .then(() => {
      if (typeof createdWindow.center === 'function') {
        createdWindow.center();
      }
      return createdWindow;
    })
    .catch((error) => {
      logLine(`[assistant] failed to load: ${error instanceof Error ? error.message : String(error)}`);
      if (assistantWindow === createdWindow) {
        assistantWindow = null;
      }
      if (!createdWindow.isDestroyed() && typeof createdWindow.destroy === 'function') {
        createdWindow.destroy();
      }
      throw error;
    })
    .finally(() => {
      assistantWindowLoadPromise = null;
    });

  return assistantWindowLoadPromise;
}

async function showDesktopAssistantWindow() {
  try {
    const windowRef = await createDesktopAssistantWindow();
    if (!isDesktopWindowAvailable(windowRef)) {
      return false;
    }
    windowRef.show();
    windowRef.focus();
    notifyDesktopAssistantState();
    return true;
  } catch (_error) {
    return false;
  }
}

async function toggleDesktopAssistantWindow() {
  if (isDesktopWindowVisible(assistantWindow)) {
    assistantWindow.hide();
    return false;
  }
  return showDesktopAssistantWindow();
}

function createDesktopTray({
  iconPath = resolveDesktopAssistantTrayIconPath(),
  TrayClass = Tray,
  imageApi = nativeImage,
  menuApi = Menu,
} = {}) {
  if (isDesktopTrayAvailable()) {
    return desktopTray;
  }

  try {
    const icon = imageApi.createFromPath(iconPath);
    if (!icon || (typeof icon.isEmpty === 'function' && icon.isEmpty())) {
      throw new Error('tray icon is empty');
    }

    desktopTray = new TrayClass(icon);
    desktopTray.setToolTip('StockPulse');
    desktopTray.setContextMenu(menuApi.buildFromTemplate([
      {
        label: 'Open Floating Assistant',
        click: () => {
          void showDesktopAssistantWindow();
        },
      },
      {
        label: 'Local Models…',
        click: () => {
          void showLocalModelWindow();
        },
      },
      {
        label: 'Show Main Window',
        click: focusExistingMainWindow,
      },
      {
        label: 'Hide Main Window',
        click: hideExistingMainWindow,
      },
      { type: 'separator' },
      {
        label: 'Quit StockPulse',
        click: () => {
          desktopIsQuitting = true;
          app.quit();
        },
      },
    ]));
    desktopTray.on('double-click', () => {
      void toggleDesktopAssistantWindow();
    });
    return desktopTray;
  } catch (error) {
    desktopTray = null;
    logLine(`[assistant] tray unavailable: ${error instanceof Error ? error.message : String(error)}`);
    return null;
  }
}

function normalizeLocalModelName(rawName) {
  const name = String(rawName || '').trim();
  if (!name || name.length > DESKTOP_LOCAL_MODEL_MAX_NAME_LENGTH) {
    return null;
  }
  return DESKTOP_LOCAL_MODEL_NAME_PATTERN.test(name) ? name : null;
}

function isAllowedLocalModelPreset(modelId) {
  return DESKTOP_LOCAL_MODEL_PRESET_IDS.has(modelId);
}

function resolveLocalModelBaseUrl({ envFile = resolveLocalModelEnvPath(), sourceEnv = process.env } = {}) {
  const configured = normalizeBackendHost(
    (hasOwnValue(sourceEnv, DESKTOP_LOCAL_MODEL_BASE_URL_ENV_KEY)
      ? sourceEnv[DESKTOP_LOCAL_MODEL_BASE_URL_ENV_KEY]
      : '')
    || readEnvFileValue(envFile, DESKTOP_LOCAL_MODEL_BASE_URL_ENV_KEY, sourceEnv)
    || ''
  );
  if (!configured) {
    return DESKTOP_LOCAL_MODEL_DEFAULT_BASE_URL;
  }
  try {
    const parsed = new URL(configured);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return DESKTOP_LOCAL_MODEL_DEFAULT_BASE_URL;
    }
    return `${parsed.protocol}//${parsed.host}`;
  } catch (_error) {
    return DESKTOP_LOCAL_MODEL_DEFAULT_BASE_URL;
  }
}

function resolveLocalModelEnvPath() {
  return path.join(resolveAppDir(), '.env');
}

function resolveLocalModelSpawnEnv(sourceEnv = process.env) {
  const env = { ...sourceEnv };
  if (isMac) {
    env.PATH = extendMacDesktopBackendPath(sourceEnv.PATH);
  }
  return env;
}

function requestLocalModelJson({
  baseUrl,
  pathname,
  timeoutMs = DESKTOP_LOCAL_MODEL_REQUEST_TIMEOUT_MS,
  requestImpl = null,
} = {}) {
  return new Promise((resolve, reject) => {
    let target;
    try {
      target = new URL(pathname, `${baseUrl}/`);
    } catch (error) {
      reject(error instanceof Error ? error : new Error(String(error)));
      return;
    }
    const transport = requestImpl
      || (target.protocol === 'https:' ? https.request : http.request);
    let settled = false;

    const req = transport(
      target,
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
      },
      (response) => {
        const chunks = [];
        response.on('data', (chunk) => {
          chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk)));
        });
        response.on('end', () => {
          if (settled) {
            return;
          }
          settled = true;
          const text = Buffer.concat(chunks).toString('utf-8');
          const statusCode = response.statusCode || 0;
          if (statusCode < 200 || statusCode >= 300) {
            reject(new Error(`Local model runtime responded with status ${statusCode}`));
            return;
          }
          if (!text) {
            resolve({});
            return;
          }
          try {
            resolve(JSON.parse(text));
          } catch (_error) {
            reject(new Error('Failed to parse local model runtime response.'));
          }
        });
        response.on('error', (error) => {
          if (settled) {
            return;
          }
          settled = true;
          reject(error);
        });
      }
    );

    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error(`Local model runtime timeout after ${timeoutMs}ms`));
    });
    req.on('error', (error) => {
      if (settled) {
        return;
      }
      settled = true;
      reject(error);
    });
    req.end();
  });
}

function requestLocalModelPullStream({
  baseUrl,
  modelId,
  timeoutMs = DESKTOP_LOCAL_MODEL_PULL_TIMEOUT_MS,
  requestImpl = null,
  onProgress = () => undefined,
} = {}) {
  return new Promise((resolve, reject) => {
    let target;
    try {
      target = new URL('/api/pull', `${baseUrl}/`);
    } catch (error) {
      reject(error instanceof Error ? error : new Error(String(error)));
      return;
    }
    const transport = requestImpl
      || (target.protocol === 'https:' ? https.request : http.request);
    const payload = Buffer.from(JSON.stringify({ name: modelId, stream: true }), 'utf-8');
    let settled = false;
    let buffer = '';
    let lastStatus = '';

    const finish = (fn, value) => {
      if (settled) {
        return;
      }
      settled = true;
      fn(value);
    };

    const consumeLine = (line) => {
      const trimmed = line.trim();
      if (!trimmed) {
        return;
      }
      let event;
      try {
        event = JSON.parse(trimmed);
      } catch (_error) {
        return;
      }
      if (event.error) {
        finish(reject, new Error(String(event.error)));
        return;
      }
      if (typeof event.status === 'string') {
        lastStatus = event.status;
      }
      const total = Number(event.total);
      const completed = Number(event.completed);
      const percent = Number.isFinite(total) && total > 0 && Number.isFinite(completed)
        ? Math.max(0, Math.min(100, Math.round((completed / total) * 100)))
        : null;
      onProgress({ status: lastStatus, percent });
    };

    const req = transport(
      target,
      {
        method: 'POST',
        headers: {
          Accept: 'application/x-ndjson',
          'Content-Type': 'application/json',
          'Content-Length': payload.length,
        },
      },
      (response) => {
        const statusCode = response.statusCode || 0;
        if (statusCode < 200 || statusCode >= 300) {
          finish(reject, new Error(`Local model pull failed with status ${statusCode}`));
          response.resume();
          return;
        }
        response.setEncoding('utf-8');
        response.on('data', (chunk) => {
          buffer += chunk;
          let newlineIndex = buffer.indexOf('\n');
          while (newlineIndex !== -1) {
            consumeLine(buffer.slice(0, newlineIndex));
            buffer = buffer.slice(newlineIndex + 1);
            newlineIndex = buffer.indexOf('\n');
          }
        });
        response.on('end', () => {
          if (buffer) {
            consumeLine(buffer);
            buffer = '';
          }
          finish(resolve, { status: lastStatus });
        });
        response.on('error', (error) => finish(reject, error));
      }
    );

    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error(`Local model pull timeout after ${timeoutMs}ms`));
    });
    req.on('error', (error) => finish(reject, error));
    req.write(payload);
    req.end();
  });
}

function extractLocalModelNames(tagsResponse) {
  if (!tagsResponse || !Array.isArray(tagsResponse.models)) {
    return [];
  }
  const names = [];
  for (const entry of tagsResponse.models) {
    const name = normalizeLocalModelName(entry && entry.name);
    if (name && !names.includes(name)) {
      names.push(name);
    }
  }
  return names.sort();
}

function probeLocalModelBinary({
  spawnImpl = spawn,
  timeoutMs = DESKTOP_LOCAL_MODEL_DETECT_TIMEOUT_MS,
} = {}) {
  return new Promise((resolve) => {
    let child;
    try {
      child = spawnImpl(DESKTOP_LOCAL_MODEL_BINARY, ['--version'], {
        env: resolveLocalModelSpawnEnv(),
        windowsHide: true,
        stdio: 'ignore',
      });
    } catch (_error) {
      resolve(false);
      return;
    }
    let settled = false;
    const done = (installed) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      resolve(installed);
    };
    const timer = setTimeout(() => {
      if (child && typeof child.kill === 'function') {
        try {
          child.kill();
        } catch (_error) {
          // ignore
        }
      }
      done(false);
    }, timeoutMs);
    child.on('error', () => done(false));
    child.on('exit', (code) => done(code === 0));
  });
}

async function detectLocalModelRuntime({
  baseUrl = resolveLocalModelBaseUrl(),
  requestImpl = null,
  spawnImpl = spawn,
} = {}) {
  const managed = Boolean(
    localModelServeProcess
    && localModelServeProcess.exitCode === null
    && !localModelServeProcess.signalCode
  );
  try {
    const tags = await requestLocalModelJson({
      baseUrl,
      pathname: '/api/tags',
      timeoutMs: DESKTOP_LOCAL_MODEL_DETECT_TIMEOUT_MS,
      requestImpl,
    });
    return {
      status: DESKTOP_LOCAL_MODEL_STATUS.RUNNING,
      installed: true,
      installedModels: extractLocalModelNames(tags),
      managed,
      baseUrl,
    };
  } catch (_error) {
    const installed = await probeLocalModelBinary({ spawnImpl });
    return {
      status: installed
        ? DESKTOP_LOCAL_MODEL_STATUS.STOPPED
        : DESKTOP_LOCAL_MODEL_STATUS.NOT_INSTALLED,
      installed,
      installedModels: [],
      managed: false,
      baseUrl,
    };
  }
}

function buildLocalModelState(overrides = {}) {
  const base = localModelState || {
    runtime: DESKTOP_LOCAL_MODEL_RUNTIME,
    status: DESKTOP_LOCAL_MODEL_STATUS.UNKNOWN,
    installed: false,
    installedModels: [],
    registeredModels: [],
    managed: false,
    baseUrl: DESKTOP_LOCAL_MODEL_DEFAULT_BASE_URL,
    operation: null,
    progress: null,
    message: '',
  };
  return { ...base, ...overrides };
}

function setLocalModelState(nextState) {
  localModelState = buildLocalModelState(nextState);
  notifyLocalModelState();
  return localModelState;
}

function readRegisteredLocalModels(envFile = resolveLocalModelEnvPath()) {
  const values = readEnvFileValues(envFile);
  const channels = String(values.LLM_CHANNELS || '')
    .split(',')
    .map((entry) => entry.trim().toLowerCase())
    .filter(Boolean);
  if (!channels.includes(DESKTOP_LOCAL_MODEL_RUNTIME)) {
    return [];
  }
  return String(values.LLM_OLLAMA_MODELS || '')
    .split(',')
    .map((entry) => normalizeLocalModelName(entry))
    .filter(Boolean);
}

function notifyLocalModelState() {
  if (!isDesktopWindowAvailable(localModelWindow)
    || !localModelWindow.webContents
    || (typeof localModelWindow.webContents.isDestroyed === 'function'
      && localModelWindow.webContents.isDestroyed())) {
    return false;
  }
  localModelWindow.webContents.send(
    DESKTOP_LOCAL_MODEL_STATE_EVENT,
    buildLocalModelState()
  );
  return true;
}

async function refreshLocalModelState({ requestImpl = null, spawnImpl = spawn } = {}) {
  const baseUrl = resolveLocalModelBaseUrl();
  const detection = await detectLocalModelRuntime({ baseUrl, requestImpl, spawnImpl });
  return setLocalModelState({
    ...detection,
    registeredModels: readRegisteredLocalModels(),
    operation: null,
    progress: null,
  });
}

async function startManagedLocalModelRuntime({
  requestImpl = null,
  spawnImpl = spawn,
  startTimeoutMs = DESKTOP_LOCAL_MODEL_START_TIMEOUT_MS,
} = {}) {
  const baseUrl = resolveLocalModelBaseUrl();
  const detection = await detectLocalModelRuntime({ baseUrl, requestImpl, spawnImpl });
  if (detection.status === DESKTOP_LOCAL_MODEL_STATUS.RUNNING) {
    return setLocalModelState({
      ...detection,
      registeredModels: readRegisteredLocalModels(),
      operation: null,
      message: '',
    });
  }
  if (detection.status === DESKTOP_LOCAL_MODEL_STATUS.NOT_INSTALLED) {
    return setLocalModelState({
      ...detection,
      registeredModels: readRegisteredLocalModels(),
      operation: null,
      message: 'Ollama is not installed. Install it to run local models.',
    });
  }

  setLocalModelState({
    ...detection,
    status: DESKTOP_LOCAL_MODEL_STATUS.STARTING,
    operation: 'start',
    message: '',
  });

  let child;
  try {
    child = spawnImpl(DESKTOP_LOCAL_MODEL_BINARY, ['serve'], {
      env: resolveLocalModelSpawnEnv(),
      windowsHide: true,
      stdio: 'ignore',
      detached: false,
    });
  } catch (error) {
    logLine(`[local-model] failed to start runtime: ${error instanceof Error ? error.message : String(error)}`);
    return setLocalModelState({
      ...detection,
      status: DESKTOP_LOCAL_MODEL_STATUS.ERROR,
      operation: null,
      message: 'Could not start the local model runtime.',
    });
  }

  localModelServeProcess = child;
  child.on('exit', () => {
    if (localModelServeProcess === child) {
      localModelServeProcess = null;
    }
  });
  child.on('error', (error) => {
    logLine(`[local-model] runtime process error: ${error instanceof Error ? error.message : String(error)}`);
  });

  const deadline = Date.now() + startTimeoutMs;
  while (Date.now() < deadline) {
    await sleep(500);
    try {
      const tags = await requestLocalModelJson({
        baseUrl,
        pathname: '/api/tags',
        timeoutMs: DESKTOP_LOCAL_MODEL_REQUEST_TIMEOUT_MS,
        requestImpl,
      });
      return setLocalModelState({
        status: DESKTOP_LOCAL_MODEL_STATUS.RUNNING,
        installed: true,
        installedModels: extractLocalModelNames(tags),
        registeredModels: readRegisteredLocalModels(),
        managed: true,
        baseUrl,
        operation: null,
        message: '',
      });
    } catch (_error) {
      // keep polling until the deadline
    }
  }

  return setLocalModelState({
    status: DESKTOP_LOCAL_MODEL_STATUS.ERROR,
    installed: true,
    managed: Boolean(localModelServeProcess),
    baseUrl,
    operation: null,
    message: 'The local model runtime did not become ready in time.',
  });
}

function stopManagedLocalModelRuntime() {
  const child = localModelServeProcess;
  if (!child || child.exitCode !== null || child.signalCode) {
    localModelServeProcess = null;
    return setLocalModelState({
      status: DESKTOP_LOCAL_MODEL_STATUS.STOPPED,
      managed: false,
      operation: null,
      message: '',
    });
  }
  try {
    if (isWindows) {
      spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true })
        .on('error', () => undefined);
    } else if (typeof child.kill === 'function') {
      child.kill('SIGTERM');
    }
  } catch (error) {
    logLine(`[local-model] failed to stop runtime: ${error instanceof Error ? error.message : String(error)}`);
  }
  localModelServeProcess = null;
  return setLocalModelState({
    status: DESKTOP_LOCAL_MODEL_STATUS.STOPPED,
    managed: false,
    operation: null,
    message: '',
  });
}

async function pullLocalModel(rawModelId, { requestImpl = null } = {}) {
  const modelId = normalizeLocalModelName(rawModelId);
  if (!modelId || !isAllowedLocalModelPreset(modelId)) {
    return {
      ok: false,
      error: 'model-not-allowed',
      message: 'Only recommended local models can be downloaded.',
    };
  }
  const baseUrl = resolveLocalModelBaseUrl();

  setLocalModelState({
    operation: 'pull',
    progress: { modelId, percent: null, status: 'starting' },
    message: '',
  });

  try {
    await requestLocalModelPullStream({
      baseUrl,
      modelId,
      requestImpl,
      onProgress: ({ status, percent }) => {
        setLocalModelState({
          operation: 'pull',
          progress: { modelId, percent, status },
        });
      },
    });
  } catch (error) {
    logLine(`[local-model] pull failed model=${modelId}`);
    await refreshLocalModelState();
    return {
      ok: false,
      error: 'pull-failed',
      message: `Could not download ${modelId}. ${error instanceof Error ? error.message : ''}`.trim(),
    };
  }

  await refreshLocalModelState();
  return { ok: true, modelId };
}

function composeCsvValue(existingRaw, additions) {
  const seen = new Set();
  const ordered = [];
  const push = (value) => {
    const token = String(value || '').trim();
    if (!token || seen.has(token)) {
      return;
    }
    seen.add(token);
    ordered.push(token);
  };
  String(existingRaw || '').split(',').forEach(push);
  additions.forEach(push);
  return ordered.join(',');
}

function upsertEnvLine(lines, key, value) {
  const assignment = `${key}=${value}`;
  const matcher = new RegExp(`^\\uFEFF?\\s*(?:export\\s+)?${key}\\s*=`);
  let replaced = false;
  const nextLines = lines.map((line) => {
    if (!replaced && matcher.test(line)) {
      replaced = true;
      return assignment;
    }
    return line;
  });
  if (!replaced) {
    nextLines.push(assignment);
  }
  return nextLines;
}

function applyLocalModelRegistration(envFile, modelId, { baseUrl = resolveLocalModelBaseUrl() } = {}) {
  const existing = readEnvFileValues(envFile);
  const nextChannels = composeCsvValue(existing.LLM_CHANNELS, [DESKTOP_LOCAL_MODEL_RUNTIME]);
  const nextModels = composeCsvValue(existing.LLM_OLLAMA_MODELS, [modelId]);
  const registration = {
    LLM_CHANNELS: nextChannels,
    LLM_OLLAMA_PROVIDER: DESKTOP_LOCAL_MODEL_RUNTIME,
    LLM_OLLAMA_BASE_URL: baseUrl,
    LLM_OLLAMA_MODELS: nextModels,
  };

  const original = fs.existsSync(envFile) ? fs.readFileSync(envFile, 'utf-8') : '';
  const hadTrailingNewline = original.endsWith('\n') || original === '';
  let lines = original ? original.replace(/\n$/, '').split('\n') : [];
  for (const [key, value] of Object.entries(registration)) {
    lines = upsertEnvLine(lines, key, value);
  }
  const content = lines.join('\n') + (hadTrailingNewline ? '\n' : '');

  ensureDirectory(path.dirname(envFile));
  const tempPath = `${envFile}.local-model.tmp`;
  const mode = fs.existsSync(envFile) ? (fs.statSync(envFile).mode & 0o777) : 0o600;
  fs.writeFileSync(tempPath, content, { encoding: 'utf-8', mode });
  try {
    fs.chmodSync(tempPath, mode);
  } catch (_error) {
    // best-effort; some filesystems reject chmod
  }
  fs.renameSync(tempPath, envFile);

  return {
    channels: nextChannels,
    models: nextModels,
    changed: original !== content,
  };
}

function registerLocalModel(rawModelId) {
  const modelId = normalizeLocalModelName(rawModelId);
  if (!modelId) {
    return { ok: false, error: 'invalid-model', message: 'Invalid local model name.' };
  }
  const envFile = resolveLocalModelEnvPath();
  let result;
  try {
    result = applyLocalModelRegistration(envFile, modelId);
  } catch (error) {
    logLine(`[local-model] registration failed model=${modelId}`);
    return {
      ok: false,
      error: 'registration-failed',
      message: 'Could not update the local model configuration.',
    };
  }
  logLine(`[local-model] registered model=${modelId} channels=${result.channels}`);
  setLocalModelState({
    registeredModels: readRegisteredLocalModels(envFile),
    message: `Registered ${modelId}. Restart StockPulse to select it for analysis.`,
  });
  return { ok: true, modelId, restartRequired: true };
}

async function createLocalModelWindow({ BrowserWindowClass = BrowserWindow } = {}) {
  if (isDesktopWindowAvailable(localModelWindow)) {
    return localModelWindowLoadPromise || localModelWindow;
  }

  const createdWindow = new BrowserWindowClass({
    width: DESKTOP_LOCAL_MODEL_WINDOW_WIDTH,
    height: DESKTOP_LOCAL_MODEL_WINDOW_HEIGHT,
    minWidth: DESKTOP_LOCAL_MODEL_WINDOW_WIDTH,
    minHeight: 480,
    resizable: true,
    maximizable: false,
    fullscreenable: false,
    show: false,
    title: 'StockPulse Local Models',
    backgroundColor: resolveWindowBackgroundColor(),
    webPreferences: {
      preload: path.join(__dirname, 'model-preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  localModelWindow = createdWindow;

  createdWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  const denyRendererNavigation = (event) => {
    event.preventDefault();
  };
  createdWindow.webContents.on('will-navigate', denyRendererNavigation);
  createdWindow.webContents.on('will-redirect', denyRendererNavigation);
  createdWindow.once('closed', () => {
    if (localModelWindow === createdWindow) {
      localModelWindow = null;
      localModelWindowLoadPromise = null;
    }
  });

  const modelPagePath = path.join(__dirname, 'renderer', 'local-models.html');
  localModelWindowLoadPromise = Promise.resolve(createdWindow.loadFile(modelPagePath))
    .then(() => createdWindow)
    .catch((error) => {
      logLine(`[local-model] failed to load view: ${error instanceof Error ? error.message : String(error)}`);
      if (localModelWindow === createdWindow) {
        localModelWindow = null;
      }
      if (!createdWindow.isDestroyed() && typeof createdWindow.destroy === 'function') {
        createdWindow.destroy();
      }
      throw error;
    })
    .finally(() => {
      localModelWindowLoadPromise = null;
    });

  return localModelWindowLoadPromise;
}

async function showLocalModelWindow() {
  try {
    const windowRef = await createLocalModelWindow();
    if (!isDesktopWindowAvailable(windowRef)) {
      return false;
    }
    windowRef.show();
    windowRef.focus();
    void refreshLocalModelState().catch(() => undefined);
    return true;
  } catch (_error) {
    return false;
  }
}

function isLocalModelSender(event) {
  return Boolean(
    event
    && event.sender
    && isDesktopWindowAvailable(localModelWindow)
    && localModelWindow.webContents === event.sender
  );
}

function assertLocalModelSender(event) {
  if (!isLocalModelSender(event)) {
    throw new Error('Unauthorized local model IPC sender');
  }
}

async function runLocalModelOperation(operation) {
  if (localModelOperationInFlight) {
    return { ok: false, error: 'busy', message: 'Another local model operation is in progress.' };
  }
  localModelOperationInFlight = true;
  try {
    return await operation();
  } finally {
    localModelOperationInFlight = false;
  }
}

ipcMain.handle('desktop:get-update-state', () => desktopUpdateState);
ipcMain.handle('desktop:check-for-updates', () => performDesktopUpdateCheck({ manual: true }));
ipcMain.handle('desktop:install-downloaded-update', () => installDownloadedUpdate());
ipcMain.handle('desktop:open-release-page', async (_event, releaseUrl) => {
  await shell.openExternal(sanitizeReleaseUrl(releaseUrl));
  return true;
});
ipcMain.handle(DESKTOP_ASSISTANT_GET_STATE_CHANNEL, (event) => {
  assertDesktopAssistantSender(event);
  return buildDesktopAssistantState();
});
ipcMain.handle(DESKTOP_ASSISTANT_OPEN_ACTION_CHANNEL, async (event, payload = {}) => {
  assertDesktopAssistantSender(event);
  const result = await openDesktopAssistantAction(payload.action, payload.stockCode);
  if (result.ok && !result.pending && isDesktopWindowAvailable(assistantWindow)) {
    assistantWindow.hide();
  }
  return result;
});
ipcMain.handle(DESKTOP_ASSISTANT_SET_MAIN_VISIBILITY_CHANNEL, (event, visible) => {
  assertDesktopAssistantSender(event);
  if (visible === true) {
    focusExistingMainWindow();
  } else if (visible === false) {
    hideExistingMainWindow();
  } else {
    throw new TypeError('Desktop assistant visibility must be boolean');
  }
  return buildDesktopAssistantState();
});
ipcMain.handle(DESKTOP_ASSISTANT_HIDE_CHANNEL, (event) => {
  assertDesktopAssistantSender(event);
  if (isDesktopWindowAvailable(assistantWindow)) {
    assistantWindow.hide();
  }
  return true;
});
ipcMain.handle(DESKTOP_LOCAL_MODEL_GET_STATE_CHANNEL, (event) => {
  assertLocalModelSender(event);
  return buildLocalModelState({ registeredModels: readRegisteredLocalModels() });
});
ipcMain.handle(DESKTOP_LOCAL_MODEL_DETECT_CHANNEL, (event) => {
  assertLocalModelSender(event);
  return runLocalModelOperation(() => refreshLocalModelState());
});
ipcMain.handle(DESKTOP_LOCAL_MODEL_START_CHANNEL, (event) => {
  assertLocalModelSender(event);
  return runLocalModelOperation(() => startManagedLocalModelRuntime());
});
ipcMain.handle(DESKTOP_LOCAL_MODEL_STOP_CHANNEL, (event) => {
  assertLocalModelSender(event);
  return stopManagedLocalModelRuntime();
});
ipcMain.handle(DESKTOP_LOCAL_MODEL_PULL_CHANNEL, (event, payload = {}) => {
  assertLocalModelSender(event);
  return runLocalModelOperation(() => pullLocalModel(payload && payload.modelId));
});
ipcMain.handle(DESKTOP_LOCAL_MODEL_REGISTER_CHANNEL, (event, payload = {}) => {
  assertLocalModelSender(event);
  return registerLocalModel(payload && payload.modelId);
});
ipcMain.handle(DESKTOP_LOCAL_MODEL_OPEN_GUIDE_CHANNEL, async (event) => {
  assertLocalModelSender(event);
  await shell.openExternal(DESKTOP_LOCAL_MODEL_INSTALL_GUIDE_URL);
  return true;
});

async function createWindow(brandMigrationResult) {
  desktopMainPageUrl = '';
  desktopWebReady = false;
  desktopDeepLinkNavigationInFlight = false;
  backendStartError = null;
  notifyDesktopAssistantState();
  const restoreResult = isWindowsNsisInstalledApp() ? restorePackagedRuntimeStateFromBackup() : null;
  const macMigrationResult = migrateMacPackagedRuntimeState();
  initLogging();
  createDesktopTray();
  if (brandMigrationResult?.sourceDir) {
    if (brandMigrationResult.alreadyCompleted) {
      logLine(`[brand-migration] legacy user data migration already completed; rollback source retained at ${brandMigrationResult.sourceDir}`);
    } else {
      logLine(
        `[brand-migration] migrated ${brandMigrationResult.migrated.length} legacy user data files from ${brandMigrationResult.sourceDir} to ${brandMigrationResult.targetDir}; source retained for rollback`
      );
    }
  }
  if (brandMigrationResult?.skipped.length) {
    logLine(`[brand-migration] preserved ${brandMigrationResult.skipped.length} existing or unsupported target entries`);
  }
  if (brandMigrationResult?.failed.length) {
    logLine(`[brand-migration] failed entries: ${brandMigrationResult.failed.join(', ')}`);
  }
  if (brandMigrationResult?.usingLegacyFallback) {
    logLine(`[brand-migration] using legacy user data directory after a critical migration failure: ${brandMigrationResult.sourceDir}`);
  }
  if (macMigrationResult.migrated.length) {
    logLine(`[migration] migrated macOS runtime files from ${macMigrationResult.sourceDirs.join(', ')} to ${macMigrationResult.targetDir}: ${macMigrationResult.migrated.join(', ')}`);
  }
  if (macMigrationResult.skipped.length) {
    logLine(`[migration] skipped existing macOS runtime files: ${macMigrationResult.skipped.join(', ')}`);
  }
  if (macMigrationResult.failed.length) {
    logLine(`[migration] failed to migrate macOS runtime files: ${macMigrationResult.failed.join(', ')}`);
  }
  const restoreFailed = Boolean(restoreResult && restoreResult.failed.length);
  const restoreIssueDetails = restoreResult
    ? restoreResult.failed.join('；')
    : '';
  const restoreErrorMessage = restoreFailed
    ? `上次更新安装未完成或恢复运行时文件失败，已保留备份目录 ${restoreResult.backupRoot}，请确认后手动恢复并重启应用。明细：${restoreIssueDetails}`
    : '';
  setDesktopUpdateState({
    status: restoreFailed ? UPDATE_STATUS.ERROR : UPDATE_STATUS.IDLE,
    currentVersion: resolveDesktopVersion(),
    updateMode: restoreFailed ? UPDATE_MODE.MANUAL : UPDATE_MODE.AUTO,
    message: restoreErrorMessage,
  });
  const startupStartedAt = Date.now();
  const logStartup = (message) => {
    logLine(`[startup +${Date.now() - startupStartedAt}ms] ${message}`);
  };

  logStartup('createWindow started');

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: resolveWindowBackgroundColor(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      additionalArguments: [`--dsa-desktop-version=${app.getVersion()}`],
    },
  });
  logStartup('BrowserWindow created');

  if (typeof mainWindow.on === 'function') {
    mainWindow.on('close', handleMainWindowClose);
    mainWindow.on('show', notifyDesktopAssistantState);
    mainWindow.on('hide', notifyDesktopAssistantState);
    mainWindow.on('minimize', notifyDesktopAssistantState);
    mainWindow.on('restore', notifyDesktopAssistantState);
  }

  const loadingPath = path.join(__dirname, 'renderer', 'loading.html');
  const loadingPageStartedAt = Date.now();
  await mainWindow.loadFile(loadingPath);
  logStartup(`Loading page rendered in ${Date.now() - loadingPageStartedAt}ms`);

  const applyThemeBackground = () => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }
    mainWindow.setBackgroundColor(resolveWindowBackgroundColor());
  };
  nativeTheme.on('updated', applyThemeBackground);
  mainWindow.once('closed', () => {
    nativeTheme.removeListener('updated', applyThemeBackground);
    mainWindow = null;
    desktopMainPageUrl = '';
    desktopWebReady = false;
    notifyDesktopAssistantState();
  });

  const webViewStartedAt = Date.now();
  mainWindow.webContents.on('did-start-loading', () => {
    logStartup('WebContents did-start-loading');
  });
  mainWindow.webContents.on('dom-ready', () => {
    logStartup(`WebContents dom-ready (+${Date.now() - webViewStartedAt}ms after events attached)`);
  });
  mainWindow.webContents.on('did-finish-load', () => {
    logStartup(`WebContents did-finish-load (+${Date.now() - webViewStartedAt}ms after events attached)`);
  });
  mainWindow.webContents.on(
    'did-fail-load',
    (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
      logStartup(
        `WebContents did-fail-load code=${errorCode} mainFrame=${isMainFrame} url=${sanitizeUrlForLog(validatedURL)} reason=${errorDescription}`
      );
    }
  );

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  const appDir = resolveAppDir();
  const envPath = path.join(appDir, '.env');
  ensureEnvFile(envPath);
  logStartup(`Env file ready: ${envPath}`);

  const backendBindHost = resolveBackendBindHost({ envFile: envPath });
  const backendConnectHost = resolveDesktopConnectHost(backendBindHost);
  logStartup(`Backend bind host=${backendBindHost}; desktop connect host=${backendConnectHost}`);

  const portFindStartedAt = Date.now();
  const port = await findAvailablePort(8000, 8100, backendBindHost);
  logStartup(`Using port ${port} (selected in ${Date.now() - portFindStartedAt}ms)`);
  logStartup(`App directory=${appDir}`);

  const dbPath = path.join(appDir, 'data', 'stock_analysis.db');
  const logDir = path.join(appDir, 'logs');

  try {
    const launchInfo = startBackend({ port, envFile: envPath, dbPath, logDir, host: backendBindHost });
    logStartup(`Backend launch mode=${launchInfo.mode}`);
    logStartup(`Backend launch command=${launchInfo.command}`);
    logStartup(`Backend launch cwd=${launchInfo.cwd}`);
    logStartup('Waiting for backend health check');
  } catch (error) {
    backendStartError = error instanceof Error ? error : new Error(String(error));
    desktopWebReady = false;
    notifyDesktopAssistantState();
    logStartup(`Backend launch failed: ${String(error)}`);
    const errorUrl = `file://${loadingPath}?error=${encodeURIComponent(String(error))}`;
    await mainWindow.loadURL(errorUrl);
    return;
  }

  const healthUrl = buildBackendUrl(backendConnectHost, port, '/api/health');
  let lastHealthProgressLogAt = 0;
  const healthProgressLogIntervalMs = 2000;

  const onHealthProgress = (event) => {
    if (!event || event.type === 'probe_start') {
      return;
    }

    if (event.type === 'ready') {
      logStartup(`Health ready in ${event.elapsedMs}ms (attempts=${event.attempts})`);
      return;
    }

    if (event.type === 'aborted' || event.type === 'total_timeout' || event.type === 'final_error') {
      const details = event.reason || event.message || '';
      logStartup(`Health ${event.type} after ${event.elapsedMs}ms (attempts=${event.attempts}) ${details}`.trim());
      return;
    }

    const now = Date.now();
    if (now - lastHealthProgressLogAt < healthProgressLogIntervalMs) {
      return;
    }

    lastHealthProgressLogAt = now;
    let detail = '';
    if (event.type === 'probe_status') {
      detail = `status=${event.statusCode}`;
    } else if (event.type === 'probe_timeout') {
      detail = `probeTimeout=${event.requestTimeoutMs}ms`;
    } else if (event.type === 'probe_error') {
      detail = `error=${event.errorCode}:${event.errorMessage}`;
    }

    logStartup(
      `Waiting for backend health... elapsed=${event.elapsedMs}ms attempts=${event.attempts}${detail ? ` ${detail}` : ''}`
    );
  };

  try {
    const healthInfo = await waitForHealth(
      healthUrl,
      60000,
      250,
      1500,
      () => {
        if (backendStartError) {
          return `backend start error: ${backendStartError.message}`;
        }
        if (!backendProcess) {
          return 'backend process is unavailable';
        }
        if (backendProcess.exitCode !== null) {
          return `backend exited with code ${backendProcess.exitCode}`;
        }
        if (backendProcess.signalCode) {
          return `backend exited by signal ${backendProcess.signalCode}`;
        }
        return null;
      },
      onHealthProgress
    );
    logStartup(`Backend ready in ${healthInfo.elapsedMs}ms (${healthInfo.attempts} probes)`);
    const mainPageStartedAt = Date.now();
    const mainPageUrl = buildMainPageUrl(port, Date.now(), backendConnectHost);
    desktopMainPageUrl = mainPageUrl;
    const initialDeepLinkRoute = pendingDesktopDeepLinkRoute;
    const initialDeepLinkOutcome = pendingDesktopDeepLinkOutcome;
    pendingDesktopDeepLinkRoute = null;
    pendingDesktopDeepLinkOutcome = null;
    const initialPageUrl = initialDeepLinkRoute
      ? buildDesktopDeepLinkTargetUrl(mainPageUrl, initialDeepLinkRoute)
      : mainPageUrl;
    try {
      await mainWindow.loadURL(initialPageUrl);
      if (initialDeepLinkOutcome) {
        initialDeepLinkOutcome.status = 'navigated';
      }
    } catch (error) {
      if (initialDeepLinkRoute) {
        if (initialDeepLinkOutcome) {
          initialDeepLinkOutcome.status = 'failed';
        }
        throw new Error('Desktop deep-link navigation failed');
      }
      throw error;
    }
    desktopWebReady = true;
    backendStartError = null;
    desktopAssistantLastReadyAt = new Date().toISOString();
    notifyDesktopAssistantState();
    await flushPendingDesktopDeepLink();
    logStartup(
      `Main page loadURL resolved in ${Date.now() - mainPageStartedAt}ms url=${sanitizeUrlForLog(initialPageUrl)}`
    );
    logStartup(`Main UI loaded in ${Date.now() - startupStartedAt}ms`);
    if (!restoreFailed) {
      void performDesktopUpdateCheck({ notify: true });
    }
  } catch (error) {
    desktopWebReady = false;
    backendStartError = error instanceof Error ? error : new Error(String(error));
    notifyDesktopAssistantState();
    logStartup(`Startup failed while waiting for health: ${String(error)}`);
    const errorUrl = `file://${loadingPath}?error=${encodeURIComponent(String(error))}`;
    await mainWindow.loadURL(errorUrl);
  }
}

function requestPackagedSingleInstanceLock() {
  if (!app.isPackaged || typeof app.requestSingleInstanceLock !== 'function') {
    return true;
  }
  return app.requestSingleInstanceLock();
}

function focusExistingMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  if (typeof mainWindow.isMinimized === 'function' && mainWindow.isMinimized()) {
    mainWindow.restore();
  }
  if (typeof mainWindow.show === 'function') {
    mainWindow.show();
  }
  if (typeof mainWindow.focus === 'function') {
    mainWindow.focus();
  }
  notifyDesktopAssistantState();
}

async function handleDesktopSecondInstance(_event, argv) {
  focusExistingMainWindow();
  const rawUrl = extractDesktopDeepLink(argv);
  if (!rawUrl || !queueDesktopDeepLink(rawUrl)) {
    return false;
  }
  return flushPendingDesktopDeepLink();
}

async function handleDesktopOpenUrl(event, rawUrl) {
  if (event && typeof event.preventDefault === 'function') {
    event.preventDefault();
  }
  if (!queueDesktopDeepLink(rawUrl)) {
    return false;
  }
  focusExistingMainWindow();
  return flushPendingDesktopDeepLink();
}

const hasDesktopInstanceLock = requestPackagedSingleInstanceLock();
const desktopBrandMigrationResult = hasDesktopInstanceLock
  ? migrateLegacyProductUserData()
  : null;

if (hasDesktopInstanceLock) {
  registerDesktopProtocolClient();
  const initialDesktopDeepLink = extractDesktopDeepLink(process.argv);
  if (initialDesktopDeepLink) {
    queueDesktopDeepLink(initialDesktopDeepLink);
  }
  app.on('open-url', handleDesktopOpenUrl);
  app.whenReady().then(() => createWindow(desktopBrandMigrationResult));
  app.on('second-instance', handleDesktopSecondInstance);
  app.on('activate', () => {
    if (!isDesktopWindowAvailable(mainWindow)) {
      void createWindow();
      return;
    }
    focusExistingMainWindow();
  });
} else {
  app.quit();
}

app.on('window-all-closed', () => {
  if (!desktopIsQuitting && isDesktopTrayAvailable()) {
    return;
  }
  void stopBackend();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  desktopIsQuitting = true;
  if (isDesktopTrayAvailable() && typeof desktopTray.destroy === 'function') {
    desktopTray.destroy();
  }
  desktopTray = null;
  stopManagedLocalModelRuntime();
  void stopBackend();
});

module.exports = {
  DEFAULT_REQUEST_TIMEOUT_MS,
  GITHUB_OWNER,
  GITHUB_REPO,
  LATEST_RELEASE_API_URL,
  RELEASES_PAGE_URL,
  DESKTOP_ASSISTANT_GET_STATE_CHANNEL,
  DESKTOP_ASSISTANT_HIDE_CHANNEL,
  DESKTOP_ASSISTANT_OPEN_ACTION_CHANNEL,
  DESKTOP_ASSISTANT_SET_MAIN_VISIBILITY_CHANNEL,
  DESKTOP_ASSISTANT_STATE_EVENT,
  DESKTOP_LOCAL_MODEL_GET_STATE_CHANNEL,
  DESKTOP_LOCAL_MODEL_DETECT_CHANNEL,
  DESKTOP_LOCAL_MODEL_START_CHANNEL,
  DESKTOP_LOCAL_MODEL_STOP_CHANNEL,
  DESKTOP_LOCAL_MODEL_PULL_CHANNEL,
  DESKTOP_LOCAL_MODEL_REGISTER_CHANNEL,
  DESKTOP_LOCAL_MODEL_OPEN_GUIDE_CHANNEL,
  DESKTOP_LOCAL_MODEL_STATE_EVENT,
  DESKTOP_LOCAL_MODEL_INSTALL_GUIDE_URL,
  DESKTOP_LOCAL_MODEL_PRESETS,
  DESKTOP_LOCAL_MODEL_STATUS,
  DESKTOP_PROTOCOL,
  DESKTOP_PROTOCOL_HOST,
  DESKTOP_UPDATE_RUNTIME_RELATIVE_FILES,
  UPDATE_MODE,
  UPDATE_STATUS,
  buildUpdateState,
  backupPackagedRuntimeState,
  buildBackendArgs,
  checkForDesktopUpdates,
  compareVersions,
  evaluateReleaseUpdate,
  buildBackendUrl,
  buildBackendEnvironment,
  extendMacDesktopBackendPath,
  extractReleaseMetadata,
  fetchLatestReleaseJson,
  findAvailablePort,
  buildMainPageUrl,
  buildDesktopAssistantRoute,
  buildDesktopAssistantState,
  buildDesktopDeepLinkTargetUrl,
  createDesktopAssistantWindow,
  createDesktopTray,
  normalizeLocalModelName,
  isAllowedLocalModelPreset,
  resolveLocalModelBaseUrl,
  extractLocalModelNames,
  probeLocalModelBinary,
  detectLocalModelRuntime,
  startManagedLocalModelRuntime,
  stopManagedLocalModelRuntime,
  pullLocalModel,
  registerLocalModel,
  applyLocalModelRegistration,
  readRegisteredLocalModels,
  buildLocalModelState,
  composeCsvValue,
  upsertEnvLine,
  createLocalModelWindow,
  extractDesktopDeepLink,
  flushPendingDesktopDeepLink,
  handleDesktopOpenUrl,
  handleDesktopSecondInstance,
  handleMainWindowClose,
  isWindowsNsisInstalledApp,
  migrateMacPackagedRuntimeState,
  migrateLegacyProductUserData,
  normalizeVersionString,
  parseSemver,
  parseDesktopDeepLink,
  queueDesktopDeepLink,
  readEnvFileValue,
  requestPackagedSingleInstanceLock,
  registerDesktopProtocolClient,
  resolveDesktopAssistantTrayIconPath,
  resolveAppDir,
  resolveLegacyProductUserDataDirs,
  resolveBackendBindHost,
  resolveDesktopConnectHost,
  resolveDesktopProviderDailyCacheDir,
  restorePackagedRuntimeStateFromBackup,
  sanitizeReleaseUrl,
  startBackend,
  stopBackend,
  __getBackendProcessForTest() {
    return backendProcess;
  },
  __setBackendProcessForTest,
  __setMainWindowForTest(mainWindowRef = null) {
    mainWindow = mainWindowRef;
  },
  __setAssistantWindowForTest(assistantWindowRef = null) {
    assistantWindow = assistantWindowRef;
    assistantWindowLoadPromise = null;
  },
  __setDesktopTrayForTest(trayRef = null) {
    desktopTray = trayRef;
  },
  __setDesktopIsQuittingForTest(isQuitting = false) {
    desktopIsQuitting = isQuitting;
  },
  __setDesktopAssistantStateForTest({
    webReady = false,
    startError = null,
    lastReadyAt = '',
  } = {}) {
    desktopWebReady = webReady;
    backendStartError = startError;
    desktopAssistantLastReadyAt = lastReadyAt;
  },
  __setDesktopDeepLinkStateForTest({
    mainPageUrl = '',
    ready = false,
    pendingRoute = null,
  } = {}) {
    desktopMainPageUrl = mainPageUrl;
    desktopWebReady = ready;
    pendingDesktopDeepLinkRoute = pendingRoute;
    pendingDesktopDeepLinkOutcome = null;
    desktopDeepLinkNavigationInFlight = false;
  },
  __getPendingDesktopDeepLinkRouteForTest() {
    return pendingDesktopDeepLinkRoute;
  },
  __setLocalModelWindowForTest(windowRef = null) {
    localModelWindow = windowRef;
    localModelWindowLoadPromise = null;
  },
  __setLocalModelServeProcessForTest(processRef = null) {
    localModelServeProcess = processRef;
  },
  __getLocalModelServeProcessForTest() {
    return localModelServeProcess;
  },
  __setLocalModelStateForTest(stateRef = null) {
    localModelState = stateRef;
    localModelOperationInFlight = false;
  },
  waitForBackendExit,
};
