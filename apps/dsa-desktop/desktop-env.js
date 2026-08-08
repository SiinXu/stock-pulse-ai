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

function listCandidateExecutableNames(command, platform = process.platform) {
  const name = String(command || '').trim();
  if (!isSafeDiagnosticCliName(name)) {
    return [];
  }
  if (platform !== 'win32') {
    return [name];
  }
  const lower = name.toLowerCase();
  if (lower.endsWith('.exe') || lower.endsWith('.cmd') || lower.endsWith('.bat')) {
    return [name];
  }
  return [`${name}.exe`, `${name}.cmd`, `${name}.bat`, name];
}

function pathLooksExecutable(filePath, platform = process.platform, { fsImpl = fs } = {}) {
  try {
    const stats = fsImpl.statSync(filePath);
    if (!stats.isFile()) {
      return false;
    }
    if (platform === 'win32') {
      return true;
    }
    // Owner/group/other execute bit (matches common CLI install modes).
    return (stats.mode & 0o111) !== 0;
  } catch (_error) {
    return false;
  }
}

/**
 * Resolve a command basename on an effective PATH without shelling out.
 * Returns the first absolute path that exists as an executable file, or null.
 */
function resolveCommandOnPath(
  command,
  pathEnv,
  {
    platform = process.platform,
    fsImpl = fs,
    pathImpl = path,
  } = {}
) {
  if (!isSafeDiagnosticCliName(command)) {
    return null;
  }

  const entries = splitPathEntries(pathEnv, platform);
  const candidates = listCandidateExecutableNames(command, platform);

  for (const entry of entries) {
    if (!entry || entry.includes('\0')) {
      continue;
    }
    for (const fileName of candidates) {
      const absolutePath = pathImpl.join(entry, fileName);
      if (pathLooksExecutable(absolutePath, platform, { fsImpl })) {
        return absolutePath;
      }
    }
  }

  return null;
}

/**
 * Operator-facing PATH/CLI diagnostics for Desktop (#884).
 * Does not mutate env, does not run CLIs, and never includes env file values.
 */
function buildDesktopEnvironmentDiagnostics({
  platform = process.platform,
  sourceEnv = process.env,
  appDir = '',
  envFile = '',
  envFileExists = null,
  commands = DESKTOP_DIAGNOSTIC_CLI_COMMANDS,
  fsImpl = fs,
  pathImpl = path,
  nowMs = Date.now(),
} = {}) {
  const processPath = String((sourceEnv && sourceEnv.PATH) || '');
  const effectivePath = resolveDesktopEffectivePath(processPath, platform);
  const processPathEntries = splitPathEntries(processPath, platform);
  const effectivePathEntries = splitPathEntries(effectivePath, platform);
  const pathAugmented = effectivePath !== processPath;
  const safeCommands = (Array.isArray(commands) ? commands : DESKTOP_DIAGNOSTIC_CLI_COMMANDS)
    .map((name) => String(name || '').trim())
    .filter((name) => isSafeDiagnosticCliName(name));

  const cli = safeCommands.map((name) => {
    const resolvedPath = resolveCommandOnPath(name, effectivePath, {
      platform,
      fsImpl,
      pathImpl,
    });
    return {
      name,
      found: Boolean(resolvedPath),
      path: resolvedPath,
    };
  });

  let resolvedEnvFileExists = envFileExists;
  if (resolvedEnvFileExists === null && envFile) {
    try {
      resolvedEnvFileExists = fsImpl.existsSync(envFile);
    } catch (_error) {
      resolvedEnvFileExists = false;
    }
  }

  return {
    schemaVersion: 1,
    generatedAt: new Date(nowMs).toISOString(),
    platform,
    path: {
      process: processPath,
      effective: effectivePath,
      processEntryCount: processPathEntries.length,
      effectiveEntryCount: effectivePathEntries.length,
      processEntries: processPathEntries,
      effectiveEntries: effectivePathEntries,
      macHomebrewAugmented: platform === 'darwin' && pathAugmented,
      augmented: pathAugmented,
      policy: platform === 'darwin'
        ? 'macos-gui-homebrew-extend'
        : 'inherit-process-path',
    },
    cli,
    runtime: {
      appDir: appDir || null,
      envFile: envFile || null,
      envFileExists: resolvedEnvFileExists === null ? null : Boolean(resolvedEnvFileExists),
    },
    notes: [
      'CLI resolution uses the effective Desktop PATH (macOS GUI apps may lack login-shell entries until Homebrew dirs are appended).',
      'Local CLI generation backends (codex/claude/opencode) inherit a sanitized env from the backend; secrets stay denylisted.',
      'Ollama also has a dedicated Local Models panel with system/embedded runtime detection beyond bare PATH lookup.',
    ],
  };
}

function summarizeDesktopEnvironmentDiagnostics(diagnostics) {
  const cliSummary = (diagnostics.cli || [])
    .map((entry) => `${entry.name}=${entry.found ? 'found' : 'missing'}`)
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
  DESKTOP_DIAGNOSTIC_CLI_COMMANDS,
  MAC_DESKTOP_CLI_PATH_ENTRIES,
  MAC_DESKTOP_SYSTEM_PATH_ENTRIES,
  buildDesktopEnvironmentDiagnostics,
  extendMacDesktopBackendPath,
  getPathDelimiter,
  hasOwnValue,
  isSafeDiagnosticCliName,
  normalizeBackendHost,
  readEnvFileValue,
  readEnvFileValues,
  resolveCommandOnPath,
  resolveDesktopEffectivePath,
  splitPathEntries,
  summarizeDesktopEnvironmentDiagnostics,
};
