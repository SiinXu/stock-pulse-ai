// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

'use strict';

const fs = require('fs');

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

function hasOwnValue(object, key) {
  return Object.prototype.hasOwnProperty.call(object || {}, key);
}

// Keep the legacy name for main.js compatibility; the PATH policy is shared by Desktop children.
function extendMacDesktopBackendPath(rawPath, platform = process.platform) {
  if (platform !== 'darwin') {
    return rawPath;
  }

  const pathDelimiter = platform === 'win32' ? ';' : ':';
  const seen = new Set();
  const entries = String(rawPath || '')
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

  [...MAC_DESKTOP_CLI_PATH_ENTRIES, ...MAC_DESKTOP_SYSTEM_PATH_ENTRIES].forEach((entry) => {
    if (!seen.has(entry)) {
      entries.push(entry);
      seen.add(entry);
    }
  });

  return entries.join(pathDelimiter);
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
  extendMacDesktopBackendPath,
  hasOwnValue,
  normalizeBackendHost,
  readEnvFileValue,
  readEnvFileValues,
};
