'use strict';

const fs = require('fs');
const path = require('path');

const DESKTOP_BACKEND_DEFAULT_HOST = '127.0.0.1';
const PROVIDER_DAILY_CACHE_DIR_ENV_KEY = 'PROVIDER_DAILY_CACHE_DIR';
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

function createBackendRuntime({
  appRootDev,
  isWindows,
  isMac,
  spawnImpl,
  netImpl,
  httpImpl,
  TextDecoderImpl,
  modelPackAttestationEnv,
  modelPackAttestationKey,
  getIsPackaged,
  getResourcesPath,
  getSourceEnv = () => process.env,
  getIsQuitting = () => false,
  resolveEnvExamplePath,
  logLine = () => undefined,
  onUnavailable = () => undefined,
} = {}) {
  if (typeof spawnImpl !== 'function') {
    throw new TypeError('Backend runtime requires a spawn implementation');
  }
  if (!netImpl || typeof netImpl.createServer !== 'function') {
    throw new TypeError('Backend runtime requires a net implementation');
  }
  if (!httpImpl || typeof httpImpl.get !== 'function') {
    throw new TypeError('Backend runtime requires an HTTP implementation');
  }
  if (typeof TextDecoderImpl !== 'function') {
    throw new TypeError('Backend runtime requires a TextDecoder implementation');
  }

  const backendPathDelimiter = isWindows ? ';' : ':';
  let backendProcess = null;
  let backendStartError = null;

  function hasOwnValue(object, key) {
    return Object.prototype.hasOwnProperty.call(object || {}, key);
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

  function expandEnvReferences(value, values = {}, sourceEnv = getSourceEnv()) {
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

  function readEnvFileValues(envFile, sourceEnv = getSourceEnv()) {
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

  function readEnvFileValue(envFile, key, sourceEnv = getSourceEnv()) {
    const values = readEnvFileValues(envFile, sourceEnv);
    return hasOwnValue(values, key) ? values[key] : null;
  }

  function resolveDesktopProviderDailyCacheDir({
    envFile,
    dbPath,
    sourceEnv = getSourceEnv(),
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
    sourceEnv = getSourceEnv(),
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

  function extendMacDesktopBackendPath(rawPath) {
    if (!isMac) {
      return rawPath;
    }

    const seen = new Set();
    const entries = String(rawPath || '')
      .split(backendPathDelimiter)
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

    return entries.join(backendPathDelimiter);
  }

  function buildBackendEnvironment({
    envFile,
    dbPath,
    logDir,
    port = null,
    host = null,
    sourceEnv = getSourceEnv(),
    modelPackAttestationKey: attestationKey = modelPackAttestationKey,
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
    if (!/^[0-9a-f]{64}$/.test(String(attestationKey || ''))) {
      throw new TypeError('Desktop Model Pack attestation key is invalid');
    }
    env[modelPackAttestationEnv] = attestationKey;

    if (Number.isInteger(selectedPort) && selectedPort >= 1 && selectedPort <= 65535) {
      env.WEBUI_PORT = String(selectedPort);
    }

    if (isMac) {
      env.PATH = extendMacDesktopBackendPath(sourceEnv.PATH);
    }

    return env;
  }

  function resolveBackendPath(sourceEnv = getSourceEnv()) {
    if (sourceEnv.DSA_BACKEND_PATH) {
      return sourceEnv.DSA_BACKEND_PATH;
    }

    if (getIsPackaged()) {
      const backendDir = path.join(getResourcesPath(), 'backend');
      const exeName = isWindows ? 'stock_analysis.exe' : 'stock_analysis';
      const oneDirPath = path.join(backendDir, 'stock_analysis', exeName);
      if (fs.existsSync(oneDirPath)) {
        return oneDirPath;
      }
      return path.join(backendDir, exeName);
    }

    return null;
  }

  function resolvePythonPath(sourceEnv = getSourceEnv()) {
    return sourceEnv.DSA_PYTHON || 'python';
  }

  function formatCommand(command, args = []) {
    return [command, ...args]
      .map((part) => {
        const value = String(part);
        return value.includes(' ') ? `"${value}"` : value;
      })
      .join(' ');
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

  function decodeBackendOutput(data, decoder) {
    if (typeof data === 'string') {
      return data.trim();
    }
    if (!Buffer.isBuffer(data)) {
      return String(data).trim();
    }

    let decoded = decoder.decode(data, { stream: true });
    if (isWindows && decoded.includes('\uFFFD')) {
      try {
        decoded = new TextDecoderImpl('gbk', { fatal: false }).decode(data, { stream: true });
      } catch (_error) {
      }
    }

    return decoded.trim();
  }

  function findAvailablePort(
    startPort = 8000,
    endPort = 8100,
    host = DESKTOP_BACKEND_DEFAULT_HOST
  ) {
    const bindHost = normalizeBackendBindHost(host, DESKTOP_BACKEND_DEFAULT_HOST);
    return new Promise((resolve, reject) => {
      const tryPort = (port) => {
        if (port > endPort) {
          reject(new Error('No available port'));
          return;
        }

        const server = netImpl.createServer();
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

        activeRequest = httpImpl.get(url, (res) => {
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

  function getAbortReason() {
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
  }

  function notifyUnavailable() {
    onUnavailable(getSnapshot());
  }

  function resetStartError() {
    backendStartError = null;
  }

  function recordStartError(error) {
    backendStartError = error instanceof Error ? error : new Error(String(error));
    notifyUnavailable();
    return backendStartError;
  }

  async function waitUntilHealthy({
    url,
    timeoutMs = 60000,
    intervalMs = 250,
    requestTimeoutMs = 1500,
    onProgress = null,
  }) {
    try {
      const result = await waitForHealth(
        url,
        timeoutMs,
        intervalMs,
        requestTimeoutMs,
        getAbortReason,
        onProgress
      );
      resetStartError();
      return result;
    } catch (error) {
      recordStartError(error);
      throw error;
    }
  }

  function startBackend({ port, envFile, dbPath, logDir, host = null }) {
    resetStartError();
    const launchStartedAt = Date.now();
    const sourceEnv = getSourceEnv();
    const bindHost = normalizeBackendBindHost(
      normalizeBackendHost(host) || resolveBackendBindHost({ envFile, sourceEnv }),
      DESKTOP_BACKEND_DEFAULT_HOST
    );
    const env = buildBackendEnvironment({
      envFile,
      dbPath,
      logDir,
      port,
      host: bindHost,
      sourceEnv,
    });
    const args = buildBackendArgs({ host: bindHost, port });
    const backendPath = resolveBackendPath(sourceEnv);
    let launchMode = '';
    let launchCommand = '';
    let launchCwd = '';
    let launchedProcess = null;

    try {
      if (backendPath) {
        if (!fs.existsSync(backendPath)) {
          throw new Error(`Backend executable not found: ${backendPath}`);
        }
        launchMode = 'packaged';
        launchCommand = formatCommand(backendPath, args);
        launchCwd = path.dirname(backendPath);
        launchedProcess = spawnImpl(backendPath, args, {
          env,
          cwd: launchCwd,
          stdio: 'pipe',
          windowsHide: true,
        });
      } else {
        const pythonPath = resolvePythonPath(sourceEnv);
        const scriptPath = path.join(appRootDev, 'main.py');
        const pythonArgs = ['-X', 'utf8', scriptPath, ...args];
        launchMode = 'development';
        launchCommand = formatCommand(pythonPath, pythonArgs);
        launchCwd = appRootDev;
        launchedProcess = spawnImpl(pythonPath, pythonArgs, {
          env,
          cwd: launchCwd,
          stdio: 'pipe',
          windowsHide: true,
        });
      }
    } catch (error) {
      recordStartError(error);
      throw error;
    }

    backendProcess = launchedProcess;
    if (launchedProcess) {
      let firstStdoutLogged = false;
      let firstStderrLogged = false;
      const stdoutDecoder = new TextDecoderImpl('utf-8', { fatal: false });
      const stderrDecoder = new TextDecoderImpl('utf-8', { fatal: false });

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
        logLine(`[backend] failed to start: ${error.message}`);
        notifyUnavailable();
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
        if (!getIsQuitting() && !backendStartError) {
          backendStartError = new Error('Backend process exited');
        }
        logLine(`[backend] exited with code ${code}, signal ${signal || 'none'}`);
        notifyUnavailable();
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
      spawnImpl(
        'taskkill',
        ['/PID', String(processToStop.pid), '/T', '/F'],
        { windowsHide: true }
      ).on('error', () => {
      });
      return waitAndClear();
    }

    if (!processToStop.killed) {
      processToStop.kill('SIGTERM');
    }
    setTimeout(() => {
      if (processToStop.killed
        || processToStop.exitCode !== null
        || processToStop.signalCode) {
        return;
      }
      try {
        processToStop.kill('SIGKILL');
      } catch (_error) {
      }
    }, 3000);

    return waitAndClear();
  }

  function getSnapshot() {
    return Object.freeze({
      process: backendProcess,
      startError: backendStartError,
    });
  }

  function setProcessForTest(processRef = null) {
    backendProcess = processRef;
  }

  function setStartErrorForTest(error = null) {
    backendStartError = error;
  }

  return Object.freeze({
    buildBackendArgs,
    buildBackendEnvironment,
    buildBackendUrl,
    decodeBackendOutput,
    ensureEnvFile,
    extendMacDesktopBackendPath,
    findAvailablePort,
    getSnapshot,
    normalizeBackendHost,
    readEnvFileValue,
    readEnvFileValues,
    recordStartError,
    resetStartError,
    resolveBackendBindHost,
    resolveDesktopConnectHost,
    resolveDesktopProviderDailyCacheDir,
    setProcessForTest,
    setStartErrorForTest,
    startBackend,
    stopBackend,
    waitForBackendExit,
    waitForHealth,
    waitUntilHealthy,
  });
}

module.exports = {
  DESKTOP_BACKEND_DEFAULT_HOST,
  createBackendRuntime,
};
