const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');
const { spawn } = require('child_process');
const { TextDecoder } = require('util');
const {
  extendMacDesktopBackendPath,
  hasOwnValue,
  normalizeBackendHost,
  readEnvFileValue,
} = require('./desktop-env');

const DESKTOP_BACKEND_DEFAULT_HOST = '127.0.0.1';
const PROVIDER_DAILY_CACHE_DIR_ENV_KEY = 'PROVIDER_DAILY_CACHE_DIR';
const PUBLIC_BIND_HOSTS = Object.freeze(new Set(['0.0.0.0', '::', '[::]', '*']));

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

function resolveDesktopProviderDailyCacheDir({
  envFile,
  dbPath,
  sourceEnv = process.env,
} = {}, dependencies = {}) {
  const sourceValue = hasOwnValue(sourceEnv, PROVIDER_DAILY_CACHE_DIR_ENV_KEY)
    ? String(sourceEnv[PROVIDER_DAILY_CACHE_DIR_ENV_KEY] || '').trim()
    : '';
  if (sourceValue) {
    return sourceValue;
  }

  const envFileValue = String(
    readEnvFileValue(
      envFile,
      PROVIDER_DAILY_CACHE_DIR_ENV_KEY,
      sourceEnv,
      dependencies
    ) || ''
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
} = {}, dependencies = {}) {
  const sourceHost = normalizeBackendHost(sourceEnv.WEBUI_HOST);
  if (sourceHost) {
    return normalizeBackendBindHost(sourceHost, fallback);
  }

  const envFileHost = normalizeBackendHost(
    readEnvFileValue(envFile, 'WEBUI_HOST', sourceEnv, dependencies)
  );
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
  modelPackAttestationEnv,
  modelPackAttestationKey,
}, {
  fsImpl = fs,
  platform = process.platform,
} = {}) {
  const selectedPort = Number(port);
  const selectedHost = normalizeBackendBindHost(
    normalizeBackendHost(host) || resolveBackendBindHost(
      { envFile, sourceEnv },
      { fsImpl }
    ),
    DESKTOP_BACKEND_DEFAULT_HOST
  );
  const env = {
    ...sourceEnv,
    DSA_DESKTOP_MODE: 'true',
    ENV_FILE: envFile,
    DATABASE_PATH: dbPath,
    LOG_DIR: logDir,
    PROVIDER_DAILY_CACHE_DIR: resolveDesktopProviderDailyCacheDir(
      { envFile, dbPath, sourceEnv },
      { fsImpl }
    ),
    PYTHONUTF8: '1',
    PYTHONIOENCODING: 'utf-8',
    WEBUI_HOST: selectedHost,
    WEBUI_ENABLED: 'false',
    BOT_ENABLED: 'false',
    DINGTALK_STREAM_ENABLED: 'false',
    FEISHU_STREAM_ENABLED: 'false',
  };
  if (!/^[0-9a-f]{64}$/.test(String(modelPackAttestationKey || ''))) {
    throw new TypeError('Desktop Model Pack attestation key is invalid');
  }
  env[modelPackAttestationEnv] = modelPackAttestationKey;

  if (Number.isInteger(selectedPort) && selectedPort >= 1 && selectedPort <= 65535) {
    env.WEBUI_PORT = String(selectedPort);
  }

  if (platform === 'darwin') {
    env.PATH = extendMacDesktopBackendPath(sourceEnv.PATH, platform);
  }

  return env;
}

function decodeBackendOutput(data, decoder, platform = process.platform) {
  if (typeof data === 'string') {
    return data.trim();
  }
  if (!Buffer.isBuffer(data)) {
    return String(data).trim();
  }

  let decoded = decoder.decode(data, { stream: true });

  // Windows subprocesses may emit local-code-page bytes; use GBK when UTF-8 replacement characters appear.
  if (platform === 'win32' && decoded.includes('\uFFFD')) {
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

function findAvailablePort(
  startPort = 8000,
  endPort = 8100,
  host = DESKTOP_BACKEND_DEFAULT_HOST,
  {
    netImpl = net,
  } = {}
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
  onProgress = null,
  {
    httpImpl = http,
  } = {}
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

function createBackendRuntime({
  app,
  appRootDev,
  fsImpl = fs,
  httpImpl = http,
  isQuitting = () => false,
  log = () => undefined,
  markUnavailable = () => undefined,
  modelPackAttestationEnv,
  modelPackAttestationKey,
  netImpl = net,
  onUnavailable = () => undefined,
  platform = process.platform,
  processRef = process,
  spawnImpl = spawn,
} = {}) {
  if (!app || !appRootDev || !modelPackAttestationEnv) {
    throw new TypeError(
      'Backend runtime requires Electron app, development root, and attestation environment key'
    );
  }

  let backendProcess = null;
  let backendStartError = null;

  const resolveBackendPath = () => {
    if (processRef.env.DSA_BACKEND_PATH) {
      return processRef.env.DSA_BACKEND_PATH;
    }

    if (app.isPackaged) {
      const backendDir = path.join(processRef.resourcesPath, 'backend');
      const exeName = platform === 'win32' ? 'stock_analysis.exe' : 'stock_analysis';
      const oneDirPath = path.join(backendDir, 'stock_analysis', exeName);
      if (fsImpl.existsSync(oneDirPath)) {
        return oneDirPath;
      }
      return path.join(backendDir, exeName);
    }

    return null;
  };

  const resolveBindHost = ({
    envFile,
    sourceEnv = processRef.env,
    fallback = DESKTOP_BACKEND_DEFAULT_HOST,
  } = {}) => resolveBackendBindHost(
    { envFile, sourceEnv, fallback },
    { fsImpl }
  );

  const buildEnvironment = (options = {}) => buildBackendEnvironment(
    {
      ...options,
      sourceEnv: options.sourceEnv === undefined ? processRef.env : options.sourceEnv,
      modelPackAttestationEnv,
      modelPackAttestationKey: options.modelPackAttestationKey === undefined
        ? modelPackAttestationKey
        : options.modelPackAttestationKey,
    },
    { fsImpl, platform }
  );

  const clearStartError = () => {
    backendStartError = null;
  };

  const setStartError = (error = null) => {
    backendStartError = error;
  };

  const isUnavailable = () => Boolean(
    backendStartError
    || (backendProcess && (backendProcess.exitCode !== null || backendProcess.signalCode))
  );

  const start = ({ port, envFile, dbPath, logDir, host = null }) => {
    const backendPath = resolveBackendPath();
    clearStartError();
    const launchStartedAt = Date.now();
    const bindHost = normalizeBackendBindHost(
      normalizeBackendHost(host) || resolveBindHost({ envFile }),
      DESKTOP_BACKEND_DEFAULT_HOST
    );

    const env = buildEnvironment({ envFile, dbPath, logDir, port, host: bindHost });
    const args = buildBackendArgs({ host: bindHost, port });
    let launchMode = '';
    let launchCommand = '';
    let launchCwd = '';

    if (backendPath) {
      if (!fsImpl.existsSync(backendPath)) {
        throw new Error(`Backend executable not found: ${backendPath}`);
      }
      launchMode = 'packaged';
      launchCommand = formatCommand(backendPath, args);
      launchCwd = path.dirname(backendPath);
      backendProcess = spawnImpl(backendPath, args, {
        env,
        cwd: launchCwd,
        stdio: 'pipe',
        windowsHide: true,
      });
    } else {
      const pythonPath = processRef.env.DSA_PYTHON || 'python';
      const scriptPath = path.join(appRootDev, 'main.py');
      const pythonArgs = ['-X', 'utf8', scriptPath, ...args];
      launchMode = 'development';
      launchCommand = formatCommand(pythonPath, pythonArgs);
      launchCwd = appRootDev;
      backendProcess = spawnImpl(pythonPath, pythonArgs, {
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
        log(`[backend] spawned pid=${launchedProcess.pid} in ${Date.now() - launchStartedAt}ms`);
      });
      launchedProcess.on('error', (error) => {
        if (backendProcess !== launchedProcess) {
          return;
        }
        setStartError(error);
        markUnavailable();
        log(`[backend] failed to start: ${error.message}`);
        onUnavailable();
      });
      launchedProcess.stdout.on('data', (data) => {
        if (backendProcess !== launchedProcess) {
          return;
        }
        if (!firstStdoutLogged) {
          firstStdoutLogged = true;
          log(`[backend] first stdout after ${Date.now() - launchStartedAt}ms`);
        }
        log(`[backend] ${decodeBackendOutput(data, stdoutDecoder, platform)}`);
      });
      launchedProcess.stderr.on('data', (data) => {
        if (backendProcess !== launchedProcess) {
          return;
        }
        if (!firstStderrLogged) {
          firstStderrLogged = true;
          log(`[backend] first stderr after ${Date.now() - launchStartedAt}ms`);
        }
        log(`[backend] ${decodeBackendOutput(data, stderrDecoder, platform)}`);
      });
      launchedProcess.on('exit', (code, signal) => {
        if (backendProcess !== launchedProcess) {
          return;
        }
        markUnavailable();
        if (!isQuitting() && !backendStartError) {
          setStartError(new Error('Backend process exited'));
        }
        log(`[backend] exited with code ${code}, signal ${signal || 'none'}`);
        onUnavailable();
      });
    }

    return {
      mode: launchMode,
      command: launchCommand,
      cwd: launchCwd,
    };
  };

  const getHealthAbortReason = () => {
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
  };

  const waitUntilHealthy = (
    url,
    {
      timeoutMs = 60000,
      intervalMs = 250,
      requestTimeoutMs = 1500,
      onProgress = null,
    } = {}
  ) => waitForHealth(
    url,
    timeoutMs,
    intervalMs,
    requestTimeoutMs,
    getHealthAbortReason,
    onProgress,
    { httpImpl }
  );

  const clearProcessIfCurrent = (processRefToClear) => {
    if (backendProcess === processRefToClear) {
      backendProcess = null;
    }
  };

  const stop = () => {
    if (!backendProcess) {
      return Promise.resolve();
    }
    const processToStop = backendProcess;
    if (processToStop.exitCode !== null || processToStop.signalCode) {
      clearProcessIfCurrent(processToStop);
      return Promise.resolve();
    }

    const waitAndClear = () => waitForBackendExit(processToStop, 10000)
      .then((exited) => {
        if (!exited) {
          return;
        }
        clearProcessIfCurrent(processToStop);
      });

    if (platform === 'win32') {
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
  };

  return {
    buildEnvironment,
    clearStartError,
    findAvailablePort: (startPort, endPort, host) => findAvailablePort(
      startPort,
      endPort,
      host,
      { netImpl }
    ),
    isUnavailable,
    setStartError,
    start,
    stop,
    waitUntilHealthy,
    __getProcessForTest: () => backendProcess,
    __setProcessForTest: (processRefForTest = null) => {
      backendProcess = processRefForTest;
    },
  };
}

module.exports = {
  DESKTOP_BACKEND_DEFAULT_HOST,
  buildBackendArgs,
  buildBackendUrl,
  createBackendRuntime,
  resolveBackendBindHost,
  resolveDesktopConnectHost,
  resolveDesktopProviderDailyCacheDir,
  waitForBackendExit,
};
