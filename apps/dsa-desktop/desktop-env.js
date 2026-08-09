// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

'use strict';

const fs = require('fs');
const path = require('path');

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

// Generation backends and local-model CLIs that Desktop operators commonly expect
// from a login shell. Keep names stable; diagnostics never shell out or run them.
const DESKTOP_DIAGNOSTIC_CLI_COMMANDS = Object.freeze([
  'ollama',
  'codex',
  'claude',
  'opencode',
]);
const DESKTOP_DIAGNOSTIC_DEADLINE_MS = 250;
const DESKTOP_DIAGNOSTIC_MAX_PATH_ENTRIES = 64;
const DESKTOP_DIAGNOSTIC_CONCURRENCY = 4;
const DESKTOP_DIAGNOSTIC_CACHE_TTL_MS = 5 * 60 * 1000;

// Allowlisted basename only: letters, digits, dash, underscore, plus Windows extensions.
const DESKTOP_DIAGNOSTIC_CLI_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

function hasOwnValue(object, key) {
  return Object.prototype.hasOwnProperty.call(object || {}, key);
}

function getPathDelimiter(platform = process.platform) {
  return platform === 'win32' ? ';' : ':';
}

function splitPathEntries(rawPath, platform = process.platform) {
  const pathDelimiter = getPathDelimiter(platform);
  const seen = new Set();
  return String(rawPath || '')
    .split(pathDelimiter)
    .map((entry) => entry.trim())
    .filter(Boolean)
    .filter((entry) => {
      if (seen.has(entry)) {
        return false;
      }
      seen.add(entry);
      return true;
    });
}

// Keep the legacy name for main.js compatibility; the PATH policy is shared by Desktop children.
function extendMacDesktopBackendPath(rawPath, platform = process.platform) {
  if (platform !== 'darwin') {
    return rawPath;
  }

  const pathDelimiter = getPathDelimiter(platform);
  const entries = splitPathEntries(rawPath, platform);

  [...MAC_DESKTOP_CLI_PATH_ENTRIES, ...MAC_DESKTOP_SYSTEM_PATH_ENTRIES].forEach((entry) => {
    if (!entries.includes(entry)) {
      entries.push(entry);
    }
  });

  return entries.join(pathDelimiter);
}

function resolveDesktopEffectivePath(rawPath, platform = process.platform) {
  if (platform === 'darwin') {
    return extendMacDesktopBackendPath(rawPath, platform);
  }
  return String(rawPath || '');
}

function isSafeDiagnosticCliName(command) {
  const name = String(command || '').trim();
  if (!name || name.includes('/') || name.includes('\\') || name.includes('..')) {
    return false;
  }
  return DESKTOP_DIAGNOSTIC_CLI_NAME_PATTERN.test(name);
}

function listCandidateExecutableNames(
  command,
  platform = process.platform,
  pathExt = process.env.PATHEXT
) {
  const name = String(command || '').trim();
  if (!isSafeDiagnosticCliName(name)) {
    return [];
  }
  if (platform !== 'win32') {
    return [name];
  }
  const lower = name.toLowerCase();
  const extensions = String(pathExt || '.COM;.EXE;.BAT;.CMD')
    .split(';')
    .map((extension) => extension.trim())
    .filter((extension) => /^\.[A-Za-z0-9]+$/.test(extension));
  if (extensions.some((extension) => lower.endsWith(extension.toLowerCase()))) {
    return [name];
  }
  return extensions.map((extension) => `${name}${extension}`);
}

function stripQuotedPathEntry(value, platform) {
  const entry = String(value || '').trim();
  if (platform === 'win32' && entry.length >= 2 && entry.startsWith('"') && entry.endsWith('"')) {
    return entry.slice(1, -1).trim();
  }
  return entry;
}

function executableSearchPathEntries(
  rawPath,
  {
    platform = process.platform,
    cwd = process.cwd(),
    pathImpl = platform === 'win32' ? path.win32 : path,
    maxEntries = DESKTOP_DIAGNOSTIC_MAX_PATH_ENTRIES,
  } = {}
) {
  if (rawPath === undefined || rawPath === null) {
    return { entries: [], limited: false, unavailable: true };
  }
  const delimiter = getPathDelimiter(platform);
  const seen = new Set();
  const rawEntries = String(rawPath).split(delimiter);
  const entries = [];
  for (const rawEntry of rawEntries) {
    const cleaned = stripQuotedPathEntry(rawEntry, platform);
    const resolved = cleaned === ''
      ? cwd
      : pathImpl.isAbsolute(cleaned)
        ? pathImpl.normalize(cleaned)
        : pathImpl.resolve(cwd, cleaned);
    if (!resolved || resolved.includes('\0')) {
      continue;
    }
    const dedupeKey = platform === 'win32' ? resolved.toLowerCase() : resolved;
    if (seen.has(dedupeKey)) {
      continue;
    }
    seen.add(dedupeKey);
    entries.push(resolved);
    if (entries.length >= maxEntries) {
      break;
    }
  }
  return {
    entries,
    limited: rawEntries.length > entries.length && entries.length >= maxEntries,
    unavailable: false,
  };
}

async function probeExecutableCandidate(
  candidatePath,
  {
    platform = process.platform,
    fsPromises = fs.promises,
  } = {}
) {
  try {
    await fsPromises.access(
      candidatePath,
      platform === 'win32' ? fs.constants.F_OK : fs.constants.X_OK
    );
    const stats = await fsPromises.stat(candidatePath);
    return stats.isFile() ? 'available' : 'missing';
  } catch (error) {
    if (['ENOENT', 'ENOTDIR'].includes(error && error.code)) {
      return 'missing';
    }
    return 'unknown';
  }
}

async function runBoundedCandidateProbes(
  candidates,
  {
    deadlineMs = DESKTOP_DIAGNOSTIC_DEADLINE_MS,
    concurrency = DESKTOP_DIAGNOSTIC_CONCURRENCY,
    probeCandidate = probeExecutableCandidate,
  } = {}
) {
  const results = new Array(candidates.length).fill('pending');
  let cursor = 0;
  let timedOut = false;
  let timer = null;
  const worker = async () => {
    while (!timedOut) {
      const index = cursor;
      cursor += 1;
      if (index >= candidates.length) return;
      try {
        results[index] = await probeCandidate(candidates[index].path, candidates[index]);
      } catch (_error) {
        results[index] = 'unknown';
      }
    }
  };
  const workers = Array.from(
    { length: Math.min(Math.max(1, concurrency), Math.max(1, candidates.length)) },
    () => worker()
  );
  await Promise.race([
    Promise.all(workers),
    new Promise((resolve) => {
      timer = setTimeout(() => {
        timedOut = true;
        resolve();
      }, Math.max(1, deadlineMs));
    }),
  ]);
  if (timer) clearTimeout(timer);
  return { results, timedOut };
}

/** Build a path-safe, bounded diagnostic summary without running any CLI. */
async function buildDesktopEnvironmentDiagnostics({
  platform = process.platform,
  sourceEnv = process.env,
  cwd = process.cwd(),
  commands = DESKTOP_DIAGNOSTIC_CLI_COMMANDS,
  pathImpl = platform === 'win32' ? path.win32 : path,
  deadlineMs = DESKTOP_DIAGNOSTIC_DEADLINE_MS,
  concurrency = DESKTOP_DIAGNOSTIC_CONCURRENCY,
  maxPathEntries = DESKTOP_DIAGNOSTIC_MAX_PATH_ENTRIES,
  probeCandidate = probeExecutableCandidate,
  nowMs = Date.now(),
} = {}) {
  const rawProcessPath = sourceEnv && hasOwnValue(sourceEnv, 'PATH')
    ? sourceEnv.PATH
    : undefined;
  const processPath = rawProcessPath === undefined ? undefined : String(rawProcessPath);
  const effectivePath = resolveDesktopEffectivePath(processPath, platform);
  const searchPath = rawProcessPath === undefined && platform !== 'darwin'
    ? { entries: [], limited: false, unavailable: true }
    : executableSearchPathEntries(effectivePath, {
        platform,
        cwd,
        pathImpl,
        maxEntries: maxPathEntries,
      });
  const pathAugmented = platform === 'darwin'
    && effectivePath !== String(processPath || '');
  const safeCommands = (Array.isArray(commands) ? commands : DESKTOP_DIAGNOSTIC_CLI_COMMANDS)
    .map((name) => String(name || '').trim())
    .filter((name) => isSafeDiagnosticCliName(name));

  const candidates = safeCommands.flatMap((name) => (
    searchPath.entries.flatMap((entry) => (
      listCandidateExecutableNames(name, platform, sourceEnv && sourceEnv.PATHEXT)
        .map((fileName) => ({
          command: name,
          path: pathImpl.join(entry, fileName),
          platform,
        }))
    ))
  ));
  const { results } = searchPath.unavailable
    ? { results: [] }
    : await runBoundedCandidateProbes(candidates, {
        deadlineMs,
        concurrency,
        probeCandidate,
      });
  const cli = safeCommands.map((name) => {
    const commandResults = results.filter((_result, index) => candidates[index].command === name);
    if (commandResults.includes('available')) {
      return { name, status: 'available', reason: null };
    }
    if (searchPath.unavailable) {
      return { name, status: 'unknown', reason: 'path_unavailable' };
    }
    if (commandResults.includes('pending')) {
      return { name, status: 'unknown', reason: 'deadline_exceeded' };
    }
    if (commandResults.includes('unknown')) {
      return { name, status: 'unknown', reason: 'probe_error' };
    }
    return { name, status: 'missing', reason: null };
  });

  return {
    schemaVersion: 2,
    generatedAt: new Date(nowMs).toISOString(),
    platform,
    path: {
      effectiveEntryCount: searchPath.entries.length,
      limited: searchPath.limited,
      macHomebrewAugmented: platform === 'darwin' && pathAugmented,
      augmented: pathAugmented,
      policy: platform === 'darwin'
        ? 'macos-gui-homebrew-extend'
        : 'inherit-process-path',
    },
    cli,
    deadlineMs,
  };
}

function createDesktopEnvironmentDiagnosticsProbe({
  build = buildDesktopEnvironmentDiagnostics,
  cacheTtlMs = DESKTOP_DIAGNOSTIC_CACHE_TTL_MS,
  clock = Date.now,
} = {}) {
  let cached = null;
  let inFlight = null;
  return (options = {}) => {
    const now = clock();
    if (cached && now - cached.completedAt < cacheTtlMs) {
      return Promise.resolve(cached.value);
    }
    if (inFlight) return inFlight;
    inFlight = Promise.resolve()
      .then(() => build(options))
      .then((value) => {
        cached = { completedAt: clock(), value };
        return value;
      })
      .finally(() => {
        inFlight = null;
      });
    return inFlight;
  };
}

function summarizeDesktopEnvironmentDiagnostics(diagnostics) {
  const cliSummary = (diagnostics.cli || [])
    .map((entry) => `${entry.name}=${entry.status || 'unknown'}`)
    .join(' ');
  const pathInfo = diagnostics.path || {};
  return [
    `platform=${diagnostics.platform || 'unknown'}`,
    `pathPolicy=${pathInfo.policy || 'unknown'}`,
    `pathEntries=${pathInfo.effectiveEntryCount ?? 0}`,
    `pathAugmented=${pathInfo.augmented ? 'yes' : 'no'}`,
    cliSummary || 'cli=none',
  ].join(' ');
}

function normalizeBackendHost(value, fallback = '') {
  const normalized = String(value || '').trim();
  return normalized || fallback;
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

function readEnvFileValues(
  envFile,
  sourceEnv = process.env,
  { fsImpl = fs } = {}
) {
  if (!envFile || !fsImpl.existsSync(envFile)) {
    return {};
  }

  let content = '';
  try {
    content = fsImpl.readFileSync(envFile, 'utf-8');
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

function readEnvFileValue(
  envFile,
  key,
  sourceEnv = process.env,
  dependencies = {}
) {
  const values = readEnvFileValues(envFile, sourceEnv, dependencies);
  return hasOwnValue(values, key) ? values[key] : null;
}

module.exports = {
  DESKTOP_DIAGNOSTIC_CACHE_TTL_MS,
  DESKTOP_DIAGNOSTIC_CONCURRENCY,
  DESKTOP_DIAGNOSTIC_DEADLINE_MS,
  DESKTOP_DIAGNOSTIC_CLI_COMMANDS,
  MAC_DESKTOP_CLI_PATH_ENTRIES,
  MAC_DESKTOP_SYSTEM_PATH_ENTRIES,
  buildDesktopEnvironmentDiagnostics,
  createDesktopEnvironmentDiagnosticsProbe,
  executableSearchPathEntries,
  extendMacDesktopBackendPath,
  getPathDelimiter,
  hasOwnValue,
  isSafeDiagnosticCliName,
  normalizeBackendHost,
  probeExecutableCandidate,
  readEnvFileValue,
  readEnvFileValues,
  resolveDesktopEffectivePath,
  runBoundedCandidateProbes,
  splitPathEntries,
  summarizeDesktopEnvironmentDiagnostics,
};
